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
#  Broker Net Summary — neobdm.tech
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/broker/{ticker}/net")
def get_broker_net(
    ticker: str,
    date:  str = "",    # YYYY-MM-DD, kosong = auto cutoff jam 19:00
    mode:  str = "val", # "val" atau "net"
    fda:   str = "A",   # "A" all, "F" foreign, "D" domestic
    top:   int = 20,
    _: str = Depends(verify_api_key),
):
    """
    Net broker summary untuk satu tanggal — buy side vs sell side.

    Logika tanggal otomatis (kalau date kosong):
      jam server < 19:00  → pakai kemarin (data belum update)
      jam server >= 19:00 → pakai hari ini

    Response:
      ticker, date, date_fmt, mode, fda,
      buy_side  : [{broker, net_lot, net_val, sell_avg}, ...]  — net buyer terbesar
      sell_side : [{broker, net_lot, net_val, sell_avg}, ...]  — net seller terbesar
      summary   : {total_lot, total_val, net_lot, net_val}
    """
    from datetime import datetime, timedelta
    from neobdm import get_instance
    from bs_command import compute_net_sides, _build_net_map

    ticker = ticker.upper()
    mode   = mode.lower()
    fda    = fda.upper()

    if mode not in ("val", "net"):
        raise HTTPException(status_code=400, detail="mode harus 'val' atau 'net'")
    if fda not in ("A", "F", "D"):
        raise HTTPException(status_code=400, detail="fda harus 'A', 'F', atau 'D'")

    # ── Tanggal aktif ─────────────────────────────────────────────────────────
    if date:
        try:
            target_dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Format date harus YYYY-MM-DD")
    else:
        now = datetime.now()
        target_dt = now if now.hour >= 19 else now - timedelta(days=1)

    date_fmt = target_dt.strftime("%d %b %Y")
    date_str = target_dt.strftime("%Y-%m-%d")

    # ── Fetch via singleton session ───────────────────────────────────────────
    try:
        neo = get_instance()
        raw = neo.get_broker_summary(ticker, date_fmt, date_fmt)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=f"Login neobdm gagal: {e}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[broker/net] {ticker} {date_fmt}: {e}")
        raise HTTPException(status_code=500, detail=f"Fetch error: {e}")

    key_map  = {"A": "all", "F": "foreign", "D": "domestic"}
    key      = f"{mode}_{key_map[fda]}"
    raw_rows = raw.get(key, [])

    if not raw_rows:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada data broker {ticker} pada {date_fmt}"
        )

    # ── Compute net ───────────────────────────────────────────────────────────
    buy_side, sell_side = compute_net_sides(raw_rows, top_n=top)

    bmap      = _build_net_map(raw_rows)
    total_lot = sum(v["buy_lot"] + v["sell_lot"] for v in bmap.values()) / 2
    total_val = sum(v["buy_val"] + v["sell_val"] for v in bmap.values()) / 2
    net_lot   = sum(v["buy_lot"] - v["sell_lot"] for v in bmap.values())
    net_val   = sum(v["buy_val"] - v["sell_val"] for v in bmap.values())

    return {
        "ticker":   ticker,
        "date":     date_str,
        "date_fmt": date_fmt,
        "mode":     mode,
        "fda":      fda,
        "buy_side": [
            {
                "broker":   r["broker"],
                "net_lot":  round(r["net_lot"]),
                "net_val":  round(r["net_val"]),
                "sell_avg": r["sell_avg"],
            }
            for r in buy_side
        ],
        "sell_side": [
            {
                "broker":   r["broker"],
                "net_lot":  round(abs(r["net_lot"])),
                "net_val":  round(abs(r["net_val"])),
                "sell_avg": r["sell_avg"],
            }
            for r in sell_side
        ],
        "summary": {
            "total_lot": round(total_lot),
            "total_val": round(total_val),
            "net_lot":   round(net_lot),
            "net_val":   round(net_val),
        },
    }

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
#  Broker Summary — neobdm.tech
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/broker/{ticker}")
def get_broker_summary(
    ticker: str,
    start: str = "",
    end: str   = "",
    mode: str  = "val",    # "val" atau "net"
    fda: str   = "A",      # "A" all, "F" foreign, "D" domestic
    top: int   = 20,
    _: str     = Depends(verify_api_key),
):
    """
    Ambil broker summary + PNG chart dalam satu response.

    Query params:
        start  : tanggal mulai, format "dd+MMM+yyyy" (e.g. "10+Apr+2025")
        end    : tanggal akhir, format "dd+MMM+yyyy"
        mode   : "val" (default) atau "net"
        fda    : "A" all (default), "F" foreign, "D" domestic
        top    : jumlah broker ditampilkan di chart (default 20)

    Response:
        {
            "ticker"     : str,
            "start_date" : str,
            "end_date"   : str,
            "key"        : str,           # e.g. "val_all"
            "data"       : list[dict],    # raw rows
            "chart_b64"  : str,           # PNG base64 — langsung pakai di <img src="data:image/png;base64,...">
        }
    """
    import base64
    from datetime import datetime, timedelta
    from bdm_command import fetch_broker_data, build_chart, _key_from_mode_fda

    ticker = ticker.upper()
    mode   = mode.lower()
    fda    = fda.upper()

    # Default tanggal kalau tidak di-pass
    if not start:
        start = (datetime.now() - timedelta(days=5)).strftime("%d %b %Y")
    else:
        start = start.replace("+", " ")

    if not end:
        end = datetime.now().strftime("%d %b %Y")
    else:
        end = end.replace("+", " ")

    if mode not in ("val", "net"):
        raise HTTPException(status_code=400, detail="mode harus 'val' atau 'net'")
    if fda not in ("A", "F", "D"):
        raise HTTPException(status_code=400, detail="fda harus 'A', 'F', atau 'D'")

    try:
        data = fetch_broker_data(ticker, start, end, mode, fda)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=f"Login neobdm gagal: {e}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fetch error: {e}")

    key = _key_from_mode_fda(mode, fda)
    rows = data.get(key, [])

    try:
        img_bytes = build_chart(data, key=key, top_n=top)
        chart_b64 = base64.b64encode(img_bytes).decode()
    except ValueError as e:
        chart_b64 = ""
        logger.warning(f"[BDM API] Chart gagal dibuat: {e}")
    except Exception as e:
        chart_b64 = ""
        logger.warning(f"[BDM API] Chart error: {e}")

    return {
        "ticker"    : ticker,
        "start_date": data.get("start_date", start),
        "end_date"  : data.get("end_date", end),
        "key"       : key,
        "data"      : rows,
        "chart_b64" : chart_b64,
    }


@app.get("/api/broker/{ticker}/image")
def get_broker_chart_image(
    ticker: str,
    start: str = "",
    end: str   = "",
    mode: str  = "val",
    fda: str   = "A",
    top: int   = 20,
    _: str     = Depends(verify_api_key),
):
    """
    Return langsung file PNG chart broker summary.
    Cocok untuk kirim ke Telegram atau tampil di browser.
    
    Contoh curl:
        curl -H "X-API-Key: <key>" \
             "http://127.0.0.1:8000/api/broker/BBCA/image?start=10+Apr+2025&end=16+Apr+2025" \
             -o bbca_broker.png
    """
    from fastapi.responses import Response
    from datetime import datetime, timedelta
    from bdm_command import fetch_broker_data, build_chart, _key_from_mode_fda

    ticker = ticker.upper()
    mode   = mode.lower()
    fda    = fda.upper()

    if not start:
        start = (datetime.now() - timedelta(days=5)).strftime("%d %b %Y")
    else:
        start = start.replace("+", " ")
    if not end:
        end = datetime.now().strftime("%d %b %Y")
    else:
        end = end.replace("+", " ")

    try:
        data      = fetch_broker_data(ticker, start, end, mode, fda)
        key       = _key_from_mode_fda(mode, fda)
        img_bytes = build_chart(data, key=key, top_n=top)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=f"Login neobdm gagal: {e}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {e}")

    return Response(
        content=img_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{ticker}_broker.png"'},
    )


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
