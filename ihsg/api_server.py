"""
api_server.py — FastAPI internal untuk expose data IHSG ke bot eksternal (dilraba, dll)

Taruh file ini di: /home/ec2-user/package/ihsg/api_server.py

Tidak perlu dijalankan manual. Tambahkan ke main.py IHSG:

    from api_server import start_api_server
    # di dalam fungsi main(), sebelum app.run_polling():
    start_api_server()

API Key:
    Set env var sebelum jalankan bot:  export IHSG_API_KEY="ganti-dengan-key-rahasia"
    Atau ubah langsung nilai default API_KEY di bawah.
    Setiap request dari dilraba harus pakai header:  X-API-Key: <key>

Endpoints:
    GET /api/health                             → cek server (tanpa key)
    GET /api/roles/all                          → semua user roles (untuk dilraba auth)
    GET /api/roles/vip/{user_id}               → cek apakah user adalah VIP
    GET /api/ohlcv/{ticker}?days=60            → OHLCV + foreign flow historis
    GET /api/indicators/{ticker}               → semua skor indikator
    GET /api/wti/{ticker}?index=COMPOSITE      → WTI korelasi vs indeks
    GET /api/predict/{ticker}?index=COMPOSITE  → prediksi ML 3 hari
"""

import os
import sys
import logging
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
import uvicorn

logger = logging.getLogger(__name__)

# ── API Key ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("IHSG_API_KEY", "filedibuat22032026semogadi2027sayakayaraya")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def verify_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="API key tidak valid")
    return key

# ── Path ───────────────────────────────────────────────────────────────────────
JSON_DIR   = "/home/ec2-user/database/json"
INJSON_DIR = "/home/ec2-user/database/injson"

app = FastAPI(
    title="IHSG Bot API",
    description="Internal API untuk expose data saham IDX ke bot eksternal",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)


# ══════════════════════════════════════════════════════════════════════════════
#  Health check — tidak butuh API key
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
#  Roles — untuk auth dilraba dan bot eksternal lainnya
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/roles/all")
def get_all_roles(_: str = Depends(verify_api_key)):
    """Return semua user roles. Dipakai dilraba untuk auth VIP."""
    from admin.auth import load_roles, list_users
    load_roles()
    # Konversi key ke string supaya JSON-serializable
    return {str(k): v for k, v in list_users().items()}


@app.get("/api/roles/vip/{user_id}")
def check_vip(user_id: int, _: str = Depends(verify_api_key)):
    """Cek apakah satu user adalah VIP."""
    from admin.auth import load_roles, is_vip_user
    load_roles()
    return {"user_id": user_id, "is_vip": is_vip_user(user_id)}


# ══════════════════════════════════════════════════════════════════════════════
#  OHLCV + Foreign Flow historis
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/ohlcv/{ticker}")
def get_ohlcv(ticker: str, days: int = 60, _: str = Depends(verify_api_key)):
    from indicators.loader import build_stock_df

    ticker = ticker.upper()
    df = build_stock_df(ticker, JSON_DIR, max_days=max(days, 5))

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"Data tidak ditemukan untuk {ticker}")

    df = df.tail(days)

    records = []
    for _, row in df.iterrows():
        records.append({
            "date":         str(row["date"]),
            "open":         float(row.get("open", 0)),
            "high":         float(row.get("high", 0)),
            "low":          float(row.get("low", 0)),
            "close":        float(row.get("close", 0)),
            "volume":       float(row.get("volume", 0)),
            "transactions": float(row.get("transactions", 0)),
            "foreign_buy":  float(row.get("foreign_buy", 0)),
            "foreign_sell": float(row.get("foreign_sell", 0)),
            "foreign_net":  float(row.get("foreign_buy", 0)) - float(row.get("foreign_sell", 0)),
        })

    return {"ticker": ticker, "days": len(records), "data": records}


# ══════════════════════════════════════════════════════════════════════════════
#  Semua indikator skor
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/indicators/{ticker}")
def get_indicators(ticker: str, _: str = Depends(verify_api_key)):
    from scorer import calculate_all_scores
    from excel_reader import get_stock_sector_data
    from saham_command import (
        analyze_stock_volume, analyze_stock_foreign,
        get_stock_ma_data, get_foreign_summary_by_days, get_stock_margin_data,
    )

    ticker = ticker.upper()

    result = calculate_all_scores(ticker, json_dir=JSON_DIR)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Data indikator tidak ditemukan untuk {ticker}")

    detail = {}

    vol_data, vol_err = analyze_stock_volume(ticker)
    detail["volume"] = vol_data if vol_data else {"error": vol_err}

    foreign_data, foreign_err = analyze_stock_foreign(ticker)
    detail["foreign"] = foreign_data if foreign_data else {"error": foreign_err}

    ma_data, ma_err = get_stock_ma_data(ticker)
    detail["ma"] = ma_data if ma_data else {"error": ma_err}

    foreign_summary = get_foreign_summary_by_days(ticker)
    if foreign_summary:
        detail["foreign_summary"] = [
            {"period": p, "buy": b, "sell": s, "net": n}
            for p, b, s, n in foreign_summary
        ]
    else:
        detail["foreign_summary"] = []

    margin_data, margin_err = get_stock_margin_data(ticker)
    detail["margin"] = {
        "is_marginable": margin_data is not None,
        "info": margin_err if not margin_data else "Marginable",
    }

    sector_data, sector_err = get_stock_sector_data(ticker)
    if sector_data:
        sd = dict(sector_data)
        try:
            import pandas as pd
            sd["tanggal_pencatatan"] = pd.to_datetime(sd["tanggal_pencatatan"]).strftime("%Y-%m-%d")
        except Exception:
            sd["tanggal_pencatatan"] = str(sd.get("tanggal_pencatatan", ""))
        detail["sector"] = sd
    else:
        detail["sector"] = {"error": sector_err}

    return {
        "ticker": result["ticker"],
        "date":   result["date"],
        "price":  result["price"],
        "change": result["change"],
        "scores": {
            "vsa":      result["vsa"],
            "fsa":      result["fsa"],
            "vfa":      result["vfa"],
            "wcc":      result["wcc"],
            "rsi":      result["rsi"],
            "macd":     result["macd"],
            "ma":       result["ma"],
            "ip_raw":   result["ip_raw"],
            "ip_score": result["ip_score"],
            "srst":     result["srst"],
            "tight":    result["tight"],
            "fbs":      result["fbs"],
            "mgn":      result["mgn"],
            "brk":      result["brk"],
            "own":      result["own"],
            "spdr":     result["spdr"],
        },
        "total":  result["total"],
        "detail": detail,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  WTI
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/wti/{ticker}")
def get_wti(ticker: str, index: str = "COMPOSITE", _: str = Depends(verify_api_key)):
    from wti_command import calculate_wti, get_index_cache

    ticker = ticker.upper()
    index  = index.upper()

    if not get_index_cache().get(index):
        raise HTTPException(
            status_code=404,
            detail=f"Data indeks {index} tidak tersedia. Pastikan reload sudah dijalankan.",
        )

    result = calculate_wti(ticker, index_code=index)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak bisa menghitung WTI untuk {ticker}. Data tidak cukup.",
        )

    up = result["idx_up_pct"]
    dn = result["idx_dn_pct"]
    if up >= 70 and dn >= 70:
        verdict = "Sangat korelasi positif"
    elif up >= 60 and dn >= 60:
        verdict = "Korelasi positif"
    elif up <= 30 and dn <= 30:
        verdict = "Defensif / anti-korelasi"
    elif up >= 60 and dn < 50:
        verdict = "Ikut naik tapi tidak ikut naik"
    elif up < 50 and dn >= 60:
        verdict = "Ikut turun tapi tidak ikut naik"
    else:
        verdict = "Korelasi lemah / netral"

    result["verdict"] = verdict
    return {"ticker": ticker, "index": index, "result": result}


# ══════════════════════════════════════════════════════════════════════════════
#  Predict
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/predict/{ticker}")
def get_predict(ticker: str, index: str = "COMPOSITE", _: str = Depends(verify_api_key)):
    from predict_command import _predict_score, _predict_wti, run_prediction

    ticker = ticker.upper()
    index  = index.upper()

    try:
        try:
            score_pred = _predict_score(ticker)
        except Exception as e:
            score_pred = {"error": str(e)}

        try:
            wti_pred = _predict_wti(ticker, index)
        except Exception as e:
            wti_pred = {"error": str(e)}

        raw_texts = run_prediction(ticker, index)

        return {
            "ticker":      ticker,
            "index":       index,
            "score_model": score_pred,
            "wti_model":   wti_pred,
            "raw_text":    "\n\n".join(raw_texts),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
#  Fungsi untuk dipanggil dari main.py IHSG
# ══════════════════════════════════════════════════════════════════════════════

def start_api_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Jalankan FastAPI di background thread.
    Daemon=True berarti thread mati otomatis kalau main process mati.

    Tambahkan ke main.py IHSG:

        from api_server import start_api_server

        def main():
            load_roles()
            ...
            start_api_server()      # <-- tambahkan di sini
            app.run_polling(...)
    """
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info(f"✅ IHSG API Server berjalan di http://{host}:{port}")
