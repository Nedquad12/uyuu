"""
predict_command.py — Handler /predict TICKER [INDEX]

Dua model prediksi 3 hari ke depan:
  1. Score Model  : XGBoost dari history skor 14 indikator → arah harga (NAIK/NETRAL/TURUN)
  2. WTI Model    : XGBoost dari korelasi saham vs indeks  → ikut/divergen

Penggunaan:
    /predict BBCA               → Score model + WTI vs COMPOSITE
    /predict BBCA LQ45          → Score model + WTI vs LQ45
    /predict BBCA IDXFINANCE    → Score model + WTI vs IDXFINANCE

Integrasi ke main.py:
    from predict_command import register_predict_handler
    register_predict_handler(app)
"""

import asyncio
import glob
import json
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user
from backtest import (
    _build_history_df, _build_df_from_files,
    FEATURES, LABEL_UP_PCT, LABEL_DOWN_PCT, LOOKAHEAD,
    load_weights,
)
from wti_command import (
    get_index_cache, _load_stock_bars, _calc_atr14,
    IDX_THRESHOLD, ATR_DIVISOR, DEFAULT_INDEX, VALID_INDICES,
    STOCK_JSON_DIR,
)

logger = logging.getLogger(__name__)

# ── Konstanta ──────────────────────────────────────────────────────────────────
WTI_LOOKAHEAD  = 3    # bar ke depan untuk cek apakah saham ikut indeks
MIN_BARS_SCORE = 30   # minimum bar untuk score model
MIN_BARS_WTI   = 20   # minimum bar untuk WTI model

WTI_FEATURES = [
    "idx_chg",        # % perubahan indeks hari ini
    "tkr_chg",        # % perubahan saham hari ini
    "roll_corr_10",   # rolling correlation 10 hari indeks vs saham
    "roll_corr_20",   # rolling correlation 20 hari
    "idx_ma5",        # indeks close vs MA5
    "tkr_ma5",        # saham close vs MA5
    "idx_vol_ratio",  # rasio volatility indeks 5 vs 20 hari
    "tkr_vol_ratio",  # rasio volatility saham 5 vs 20 hari
    "followed_prev1", # apakah saham ikut indeks 1 bar lalu
    "followed_prev2", # apakah saham ikut indeks 2 bar lalu
    "followed_prev3", # apakah saham ikut indeks 3 bar lalu
]


# ══════════════════════════════════════════════════════════════════════════════
#  Helper: build fitur WTI dari injson + saham json
# ══════════════════════════════════════════════════════════════════════════════

def _build_wti_df(ticker: str, index_code: str) -> Optional[pd.DataFrame]:
    """
    Bangun DataFrame fitur untuk model WTI.
    Data indeks dari _INDEX_CACHE (sudah di RAM via wti_command).
    Data saham dari JSON harian.

    Label per baris = 1 jika saham mengikuti arah indeks dalam 3 hari ke depan
    (mayoritas dari hari yang tidak netral), else 0.
    """
    idx_bars = get_index_cache().get(index_code.upper())
    if not idx_bars:
        return None

    tkr_bars = _load_stock_bars(ticker, STOCK_JSON_DIR)
    if not tkr_bars:
        return None

    # ATR14 untuk threshold saham
    atr14 = _calc_atr14(tkr_bars)
    if atr14 is None:
        return None

    last_close    = tkr_bars[-1]["close"]
    atr_pct       = (atr14 / last_close) * 100
    tkr_threshold = atr_pct / ATR_DIVISOR

    # Build date map
    idx_map = {b["date"]: b["close"] for b in idx_bars}
    tkr_map = {b["date"]: b["close"] for b in tkr_bars}

    common = sorted(set(idx_map.keys()) & set(tkr_map.keys()))
    if len(common) < MIN_BARS_WTI + WTI_LOOKAHEAD + 1:
        return None

    idx_closes = [idx_map[d] for d in common]
    tkr_closes = [tkr_map[d] for d in common]

    # % change harian
    idx_chgs = [0.0]
    tkr_chgs = [0.0]
    for i in range(1, len(common)):
        ic = (idx_closes[i] - idx_closes[i-1]) / idx_closes[i-1] * 100 if idx_closes[i-1] else 0.0
        tc = (tkr_closes[i] - tkr_closes[i-1]) / tkr_closes[i-1] * 100 if tkr_closes[i-1] else 0.0
        idx_chgs.append(ic)
        tkr_chgs.append(tc)

    idx_chgs = np.array(idx_chgs)
    tkr_chgs = np.array(tkr_chgs)
    n        = len(common)

    def rolling_corr(a, b, w):
        out = np.full(n, 0.0)
        for i in range(w - 1, n):
            sa = a[i - w + 1: i + 1]
            sb = b[i - w + 1: i + 1]
            if np.std(sa) > 0 and np.std(sb) > 0:
                out[i] = float(np.corrcoef(sa, sb)[0, 1])
        return out

    def rolling_std(a, w):
        out = np.full(n, 0.0)
        for i in range(w - 1, n):
            out[i] = float(np.std(a[i - w + 1: i + 1]))
        return out

    def rolling_ma(arr, w):
        out = np.full(n, 0.0)
        for i in range(w - 1, n):
            out[i] = float(np.mean(arr[i - w + 1: i + 1]))
        return out

    rc10      = rolling_corr(idx_chgs, tkr_chgs, 10)
    rc20      = rolling_corr(idx_chgs, tkr_chgs, 20)
    idx_ma5   = rolling_ma(idx_closes, 5)
    tkr_ma5   = rolling_ma(tkr_closes, 5)
    idx_std5  = rolling_std(idx_chgs, 5)
    idx_std20 = rolling_std(idx_chgs, 20)
    tkr_std5  = rolling_std(tkr_chgs, 5)
    tkr_std20 = rolling_std(tkr_chgs, 20)

    def followed(ic, tc):
        """1 = ikut, 0 = divergen, -1 = indeks netral (tidak dihitung)."""
        idx_up   = ic >  IDX_THRESHOLD
        idx_down = ic < -IDX_THRESHOLD
        tkr_up   = tc >  tkr_threshold
        tkr_down = tc < -tkr_threshold
        if not idx_up and not idx_down:
            return -1
        if idx_up and tkr_up:
            return 1
        if idx_down and tkr_down:
            return 1
        return 0

    followed_arr = np.array([followed(idx_chgs[i], tkr_chgs[i]) for i in range(n)])

    rows = []
    for i in range(20, n - WTI_LOOKAHEAD):
        # Label: mayoritas 3 hari ke depan saham ikut indeks
        future_follow = 0
        counted       = 0
        for k in range(1, WTI_LOOKAHEAD + 1):
            fi = followed_arr[i + k]
            if fi != -1:
                counted      += 1
                future_follow += fi

        if counted == 0:
            continue
        label = 1 if (future_follow / counted) > 0.5 else 0

        idx_vol_ratio = (idx_std5[i] / idx_std20[i]) if idx_std20[i] > 0 else 1.0
        tkr_vol_ratio = (tkr_std5[i] / tkr_std20[i]) if tkr_std20[i] > 0 else 1.0
        idx_ma5_rel   = (idx_closes[i] / idx_ma5[i] - 1) * 100 if idx_ma5[i] > 0 else 0.0
        tkr_ma5_rel   = (tkr_closes[i] / tkr_ma5[i] - 1) * 100 if tkr_ma5[i] > 0 else 0.0

        fp1 = max(0, followed_arr[i])
        fp2 = max(0, followed_arr[i - 1]) if i >= 1 else 0
        fp3 = max(0, followed_arr[i - 2]) if i >= 2 else 0

        rows.append({
            "date":          common[i],
            "idx_chg":       idx_chgs[i],
            "tkr_chg":       tkr_chgs[i],
            "roll_corr_10":  rc10[i],
            "roll_corr_20":  rc20[i],
            "idx_ma5":       idx_ma5_rel,
            "tkr_ma5":       tkr_ma5_rel,
            "idx_vol_ratio": idx_vol_ratio,
            "tkr_vol_ratio": tkr_vol_ratio,
            "followed_prev1": fp1,
            "followed_prev2": fp2,
            "followed_prev3": fp3,
            "tkr_threshold": tkr_threshold,
            "label":         label,
        })

    if len(rows) < MIN_BARS_WTI:
        return None

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  Model 1: Score Prediction
# ══════════════════════════════════════════════════════════════════════════════

def _predict_score(ticker: str) -> Optional[dict]:
    """
    Train XGBoost dari history skor 14 indikator → prediksi arah harga 3 hari.
    Menggunakan _build_history_df dari backtest.py.
    """
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return {"error": "XGBoost belum terinstall. Jalankan: pip install xgboost"}

    df = _build_history_df(ticker)
    if df is None or len(df) < MIN_BARS_SCORE + 5:
        return {"error": f"Data tidak cukup untuk {ticker} (minimal {MIN_BARS_SCORE} bar)"}

    weights = load_weights(ticker)

    # Feature matrix: raw indicator scores + weighted total
    X_cols = FEATURES + ["total"]

    df["total"] = sum(
        df[f].astype(float) * float(weights.get(f, 1.0))
        for f in FEATURES
    )

    for col in X_cols:
        if col not in df.columns:
            df[col] = 0.0

    X     = df[X_cols].astype(float).values
    y_raw = df["label"].values   # -1, 0, 1
    y     = y_raw + 1            # shift → 0, 1, 2

    split   = int(len(X) * 0.7)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="mlogloss",
        random_state=42,
        verbosity=0,
        num_class=3,
        objective="multi:softmax",
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    y_pred_test = model.predict(X_test)
    win_rate    = float((y_pred_test == y_test).sum() / len(y_test)) if len(y_test) > 0 else 0.0

    X_latest   = X[-1].reshape(1, -1)
    proba      = model.predict_proba(X_latest)[0]   # [p_down, p_flat, p_up]
    label_map  = {0: "TURUN", 1: "NETRAL", 2: "NAIK"}
    pred_class = int(np.argmax(proba))
    label      = label_map[pred_class]
    confidence = float(proba[pred_class]) * 100

    importances = {X_cols[i]: float(model.feature_importances_[i]) for i in range(len(X_cols))}
    top3        = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "label":      label,
        "confidence": round(confidence, 1),
        "proba_up":   round(float(proba[2]) * 100, 1),
        "proba_down": round(float(proba[0]) * 100, 1),
        "proba_flat": round(float(proba[1]) * 100, 1),
        "n_train":    len(X_train),
        "n_test":     len(X_test),
        "win_rate":   round(win_rate * 100, 1),
        "top3_feat":  top3,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Model 2: WTI Prediction
# ══════════════════════════════════════════════════════════════════════════════

def _predict_wti(ticker: str, index_code: str) -> Optional[dict]:
    """
    Train XGBoost dari data korelasi saham vs indeks →
    prediksi apakah saham akan mengikuti indeks dalam 3 hari ke depan.
    """
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return {"error": "XGBoost belum terinstall. Jalankan: pip install xgboost"}

    df = _build_wti_df(ticker, index_code)
    if df is None or len(df) < MIN_BARS_WTI + 5:
        if df is None:
            if not get_index_cache().get(index_code.upper()):
                reason = f"Data indeks {index_code} belum ada di cache, jalankan reload"
            elif not _load_stock_bars(ticker, STOCK_JSON_DIR):
                reason = f"Data saham {ticker} tidak ditemukan"
            else:
                reason = "Data tidak cukup, pastikan reload sudah dijalankan"
        else:
            reason = f"Data terlalu sedikit ({len(df)} bar, minimal {MIN_BARS_WTI + 5})"
        return {"error": reason}

    X = df[WTI_FEATURES].astype(float).values
    y = df["label"].values   # 0 atau 1

    split   = int(len(X) * 0.7)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
        objective="binary:logistic",
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    y_pred   = model.predict(X_test)
    win_rate = float((y_pred == y_test).sum() / len(y_test)) if len(y_test) > 0 else 0.0

    X_latest    = X[-1].reshape(1, -1)
    proba       = model.predict_proba(X_latest)[0]   # [p_divergen, p_follow]
    follow_prob = float(proba[1]) * 100
    div_prob    = float(proba[0]) * 100

    if follow_prob >= div_prob:
        label      = f"IKUT {index_code.upper()}"
        confidence = follow_prob
    else:
        label      = "DIVERGEN"
        confidence = div_prob

    last_row     = df.iloc[-1]
    rc10         = float(last_row["roll_corr_10"])
    rc20         = float(last_row["roll_corr_20"])
    recent_follow = int(last_row["followed_prev1"]) + int(last_row["followed_prev2"]) + int(last_row["followed_prev3"])

    return {
        "label":         label,
        "confidence":    round(confidence, 1),
        "proba_follow":  round(follow_prob, 1),
        "proba_div":     round(div_prob, 1),
        "n_train":       len(X_train),
        "n_test":        len(X_test),
        "win_rate":      round(win_rate * 100, 1),
        "roll_corr_10":  round(rc10, 3),
        "roll_corr_20":  round(rc20, 3),
        "recent_follow": recent_follow,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Formatter
# ══════════════════════════════════════════════════════════════════════════════

def _conf_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _corr_desc(corr: float) -> str:
    if corr >= 0.7:   return "sangat kuat"
    if corr >= 0.4:   return "kuat"
    if corr >= 0.2:   return "moderat"
    if corr >= 0:     return "lemah"
    return "negatif"


def _emoji_score(label: str) -> str:
    return {"NAIK": "🟢", "TURUN": "🔴", "NETRAL": "⚪"}.get(label, "❓")


def fmt_prediction(
    ticker: str,
    index_code: str,
    score_pred: Optional[dict],
    wti_pred: Optional[dict],
) -> list[str]:
    ticker = ticker.upper()
    lines  = [
        f"🔮 <b>Prediksi 3 Hari — {ticker}</b>",
        "─────────────────────────",
        "",
    ]

    # ── Blok 1: Score Model ───────────────────────────────────────────────
    lines.append("📊 <b>Score Model (Arah Harga)</b>")

    if score_pred is None or "error" in score_pred:
        err = score_pred.get("error", "Data tidak tersedia") if score_pred else "Data tidak tersedia"
        lines.append(f"   ❌ {err}")
    else:
        sp    = score_pred
        emoji = _emoji_score(sp["label"])
        bar   = _conf_bar(sp["confidence"])
        lines += [
            f"   {emoji} <b>{sp['label']}</b>  —  Confidence: <b>{sp['confidence']:.1f}%</b>",
            f"   [{bar}]",
            f"",
            f"   Probabilitas:",
            f"   🟢 Naik   : <b>{sp['proba_up']:.1f}%</b>",
            f"   ⚪ Netral : <b>{sp['proba_flat']:.1f}%</b>",
            f"   🔴 Turun  : <b>{sp['proba_down']:.1f}%</b>",
            f"",
            f"   Train: {sp['n_train']} bar  |  Test: {sp['n_test']} bar",
            f"   Akurasi backtest: <b>{sp['win_rate']:.1f}%</b>",
        ]
        if sp.get("top3_feat"):
            top3_str = " · ".join(f"{k}({v:.2f})" for k, v in sp["top3_feat"])
            lines.append(f"   Top fitur: <code>{top3_str}</code>")

    lines += ["", "─────────────────────────", ""]

    # ── Blok 2: WTI Model ────────────────────────────────────────────────
    lines.append(f"📡 <b>WTI Model (Korelasi vs {index_code.upper()})</b>")
    lines.append(f"   Prediksi apakah <b>{ticker}</b> ikut arah <b>{index_code.upper()}</b> dalam 3 hari:")

    if wti_pred is None or "error" in wti_pred:
        err = wti_pred.get("error", "Data tidak tersedia") if wti_pred else "Data tidak tersedia"
        lines.append(f"   ❌ {err}")
    else:
        wp  = wti_pred
        bar = _conf_bar(wp["confidence"])
        follow_emoji = "🔗" if "IKUT" in wp["label"] else "🔀"
        lines += [
            f"",
            f"   {follow_emoji} <b>{wp['label']}</b>  —  Confidence: <b>{wp['confidence']:.1f}%</b>",
            f"   [{bar}]",
            f"",
            f"   Probabilitas:",
            f"   🔗 Ikut {index_code.upper():<10}: <b>{wp['proba_follow']:.1f}%</b>",
            f"   🔀 Divergen        : <b>{wp['proba_div']:.1f}%</b>",
            f"",
            f"   Korelasi historis:",
            f"   10 hari : <b>{wp['roll_corr_10']:+.3f}</b>  ({_corr_desc(wp['roll_corr_10'])})",
            f"   20 hari : <b>{wp['roll_corr_20']:+.3f}</b>  ({_corr_desc(wp['roll_corr_20'])})",
            f"",
            f"   3 hari lalu ikut indeks: <b>{wp['recent_follow']}/3</b>",
            f"   Train: {wp['n_train']} bar  |  Test: {wp['n_test']} bar",
            f"   Akurasi backtest: <b>{wp['win_rate']:.1f}%</b>",
        ]

    lines += [
        "",
        "─────────────────────────",
        "<i>⚠️ Prediksi model ML, bukan saran investasi.</i>",
        f"<i>Lookahead: {LOOKAHEAD} hari bursa ke depan.</i>",
    ]

    # Split jika terlalu panjang
    full = "\n".join(lines)
    if len(full) <= 4000:
        return [full]

    parts = full.split("─────────────────────────")
    msgs, chunk = [], ""
    for part in parts:
        if len(chunk) + len(part) > 3800:
            if chunk.strip():
                msgs.append(chunk.strip())
            chunk = part
        else:
            chunk += "─────────────────────────" + part
    if chunk.strip():
        msgs.append(chunk.strip())
    return msgs if msgs else [full[:4000]]


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_prediction(ticker: str, index_code: str = DEFAULT_INDEX) -> list[str]:
    ticker     = ticker.upper()
    index_code = index_code.upper()

    score_pred = None
    wti_pred   = None

    try:
        score_pred = _predict_score(ticker)
    except Exception as e:
        logger.error(f"[{ticker}] Score prediction error: {e}")
        score_pred = {"error": str(e)}

    try:
        wti_pred = _predict_wti(ticker, index_code)
    except Exception as e:
        logger.error(f"[{ticker}] WTI prediction error: {e}")
        wti_pred = {"error": str(e)}

    return fmt_prediction(ticker, index_code, score_pred, wti_pred)


# ══════════════════════════════════════════════════════════════════════════════
#  Telegram handler
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /predict TICKER [INDEX]

    Contoh:
        /predict BBCA
        /predict BBCA LQ45
        /predict TLKM IDXFINANCE
    """
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "  <code>/predict TICKER</code>          → vs COMPOSITE\n"
            "  <code>/predict TICKER INDEX</code>    → vs indeks pilihan\n\n"
            "<b>Contoh:</b>\n"
            "  <code>/predict BBCA</code>\n"
            "  <code>/predict BBCA LQ45</code>\n"
            "  <code>/predict TLKM IDXFINANCE</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    ticker     = args[0].upper()
    index_code = args[1].upper() if len(args) >= 2 else DEFAULT_INDEX

    # Validasi indeks
    if index_code not in VALID_INDICES and index_code not in get_index_cache():
        await update.message.reply_text(
            f"❌ Indeks <code>{index_code}</code> tidak dikenali.\n\n"
            f"Indeks yang tersedia:\n"
            f"<code>{', '.join(sorted(VALID_INDICES))}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    msg = await update.message.reply_text(
        f"⏳ Melatih model prediksi <b>{ticker}</b> vs <b>{index_code}</b>…\n"
        f"<i>Ini membutuhkan beberapa detik.</i>",
        parse_mode=ParseMode.HTML,
    )

    results = await asyncio.get_event_loop().run_in_executor(
        None, run_prediction, ticker, index_code
    )

    await msg.delete()
    for text in results:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════════════

def register_predict_handler(app) -> None:
    """Daftarkan /predict ke Application. Panggil dari main.py."""
    app.add_handler(CommandHandler("predict", cmd_predict))
