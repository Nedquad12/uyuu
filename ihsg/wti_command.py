import asyncio
import glob
import json
import logging
import os
from typing import Optional

import numpy as np
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user

logger = logging.getLogger(__name__)

# ── Path ───────────────────────────────────────────────────────────────────────
INJSON_DIR     = "/home/ec2-user/database/injson"   # JSON indeks harian
STOCK_JSON_DIR = "/home/ec2-user/database/json"      # JSON saham harian

# ── Konstanta WTI ──────────────────────────────────────────────────────────────
LOOKBACK_DAYS  = 90     # bar yang dipakai untuk analisis korelasi
ATR_PERIOD     = 14     # Wilder ATR period
ATR_DIVISOR    = 3.0    # ATR% / 3 = threshold saham
IDX_THRESHOLD  = 0.1    # threshold indeks (%) — fix untuk semua indeks
DEFAULT_INDEX  = "COMPOSITE"

# Semua kode indeks yang valid (dari file sampel)
VALID_INDICES = {
    "COMPOSITE", "LQ45", "IDXLQ45LCL", "IDX30", "IDX80",
    "IDXESGL", "IDXQ30", "IDXV30", "IDXG30", "IDXHIDIV20",
    "IDXBUMN20", "JII70", "ISSI", "JII", "IDXMESBUMN",
    "IDXSHAGROW", "IDXSMC-LIQ", "IDXSMC-COM", "MBX", "DBX",
    "ABX", "KOMPAS100", "INFOBANK15", "BISNIS-27", "INVESTOR33",
    "SRI-KEHATI", "ESGSKEHATI", "ESGQKEHATI", "SMINFRA18",
    "MNC36", "I-GRADE", "PRIMBANK10", "ECONOMIC30", "IDXVESTA28",
    "IDXENERGY", "IDXBASIC", "IDXINDUST", "IDXNONCYC", "IDXCYCLIC",
    "IDXHEALTH", "IDXFINANCE", "IDXPROPERT", "IDXTECHNO",
    "IDXINFRA", "IDXTRANS",
}

# ── RAM cache ──────────────────────────────────────────────────────────────────
# { "COMPOSITE": [{"date": "2025-01-02", "close": 7200.0, "high": ..., "low": ...}, ...] }
_INDEX_CACHE: dict[str, list[dict]] = {}


# ══════════════════════════════════════════════════════════════════════════════
#  Helper: parse tanggal dari nama file ddmmyy
# ══════════════════════════════════════════════════════════════════════════════

def _date_from_filename(fname: str) -> str | None:
    """ddmmyy.json → 'YYYY-MM-DD'. None jika format tidak cocok."""
    base = os.path.basename(fname).replace(".json", "")
    try:
        if len(base) == 6:
            d = int(base[:2])
            m = int(base[2:4])
            y = 2000 + int(base[4:6])
            return f"{y:04d}-{m:02d}-{d:02d}"
    except ValueError:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Cache builder — panggil dari main.py saat startup / reload
# ══════════════════════════════════════════════════════════════════════════════

def build_wti_index_cache(injson_dir: str = INJSON_DIR) -> dict[str, int]:
    global _INDEX_CACHE

    all_files = sorted(glob.glob(os.path.join(injson_dir, "*.json")))
    if not all_files:
        logger.warning(f"[WTI] Tidak ada file JSON di {injson_dir}")
        _INDEX_CACHE = {}
        return {}

    # Kumpulkan per indeks
    tmp: dict[str, list[dict]] = {}

    for fpath in all_files:
        date_str = _date_from_filename(fpath)
        if date_str is None:
            continue

        try:
            with open(fpath, encoding="utf-8") as f:
                records = json.load(f)
        except Exception as e:
            logger.warning(f"[WTI] Error baca {fpath}: {e}")
            continue

        for rec in records:
            code  = str(rec.get("code", "")).strip().upper()
            close = float(rec.get("close", 0))
            if not code or close <= 0:
                continue

            bar = {
                "date":  date_str,
                "close": close,
                "high":  float(rec.get("high", close)),
                "low":   float(rec.get("low",  close)),
            }

            if code not in tmp:
                tmp[code] = []
            tmp[code].append(bar)

    # Deduplikasi & sort ascending per indeks
    _INDEX_CACHE = {}
    for code, bars in tmp.items():
        bars.sort(key=lambda x: x["date"])
        seen, deduped = set(), []
        for b in bars:
            if b["date"] not in seen:
                seen.add(b["date"])
                deduped.append(b)
        _INDEX_CACHE[code] = deduped

    summary = {code: len(bars) for code, bars in _INDEX_CACHE.items()}
    logger.info(
        f"[WTI] Index cache: {len(_INDEX_CACHE)} indeks, "
        f"COMPOSITE={summary.get('COMPOSITE', 0)} bar"
    )
    return summary


def get_index_cache() -> dict[str, list[dict]]:
    return _INDEX_CACHE


# ══════════════════════════════════════════════════════════════════════════════
#  Loader saham dari JSON harian
# ══════════════════════════════════════════════════════════════════════════════

def _load_stock_bars(ticker: str, json_dir: str = STOCK_JSON_DIR) -> list[dict]:
    all_files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    bars = []

    for fpath in all_files:
        date_str = _date_from_filename(fpath)
        if date_str is None:
            continue

        try:
            with open(fpath, encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            continue

        for rec in records:
            kode = str(rec.get("Kode Saham", "")).strip().upper()
            if kode != ticker.upper():
                continue
            close = float(rec.get("Penutupan", 0))
            if close > 0:
                bars.append({
                    "date":  date_str,
                    "close": close,
                    "high":  float(rec.get("Tertinggi", close)),
                    "low":   float(rec.get("Terendah",  close)),
                })
            break   # satu saham per file

    bars.sort(key=lambda x: x["date"])
    return bars


# ══════════════════════════════════════════════════════════════════════════════
#  ATR 14 Wilder
# ══════════════════════════════════════════════════════════════════════════════

def _calc_atr14(bars: list[dict]) -> Optional[float]:
    n = len(bars)
    if n < ATR_PERIOD + 1:
        return None

    highs  = [b["high"]  for b in bars]
    lows   = [b["low"]   for b in bars]
    closes = [b["close"] for b in bars]

    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(
            highs[i]  - lows[i],
            abs(highs[i]  - closes[i - 1]),
            abs(lows[i]   - closes[i - 1]),
        ))

    atr = float(np.mean(tr[:ATR_PERIOD]))
    for i in range(ATR_PERIOD, n):
        atr = (atr * (ATR_PERIOD - 1) + tr[i]) / ATR_PERIOD

    return atr


# ══════════════════════════════════════════════════════════════════════════════
#  Core WTI calculation
# ══════════════════════════════════════════════════════════════════════════════

def calculate_wti(
    ticker: str,
    index_code: str = DEFAULT_INDEX,
    json_dir: str = STOCK_JSON_DIR,
) -> dict | None:
    """
    Hitung WTI satu ticker vs satu indeks.

    Returns:
        dict hasil, atau None jika data tidak cukup / tidak tersedia.
    """
    index_code = index_code.upper()

    # Ambil data indeks dari cache
    idx_bars = _INDEX_CACHE.get(index_code)
    if not idx_bars:
        logger.warning(f"[WTI] Indeks {index_code} tidak ada di cache")
        return None

    # Load saham (full history untuk ATR)
    tkr_bars = _load_stock_bars(ticker, json_dir)
    if not tkr_bars:
        return None

    # ATR14 dari full history
    atr14 = _calc_atr14(tkr_bars)
    if atr14 is None:
        return None

    last_close    = tkr_bars[-1]["close"]
    atr_pct       = (atr14 / last_close) * 100
    tkr_threshold = atr_pct / ATR_DIVISOR

    # Build date map
    idx_map = {b["date"]: b["close"] for b in idx_bars}
    tkr_map = {b["date"]: b["close"] for b in tkr_bars}

    # Tanggal bersama, sorted ascending
    common_dates = sorted(set(idx_map.keys()) & set(tkr_map.keys()))
    if len(common_dates) < 2:
        return None

    # Ambil 90 hari terakhir (+1 untuk prev bar)
    window = common_dates[-(LOOKBACK_DAYS + 1):]

    idx_up_total = 0
    idx_up_match = 0
    idx_dn_total = 0
    idx_dn_match = 0
    neutral_total = 0

    for i in range(1, len(window)):
        d_today = window[i]
        d_prev  = window[i - 1]

        idx_chg = (idx_map[d_today] - idx_map[d_prev]) / idx_map[d_prev] * 100
        tkr_chg = (tkr_map[d_today] - tkr_map[d_prev]) / tkr_map[d_prev] * 100

        idx_is_up   = idx_chg >  IDX_THRESHOLD
        idx_is_down = idx_chg < -IDX_THRESHOLD
        tkr_is_up   = tkr_chg >  tkr_threshold
        tkr_is_down = tkr_chg < -tkr_threshold

        if idx_is_up:
            idx_up_total += 1
            if tkr_is_up:
                idx_up_match += 1
        elif idx_is_down:
            idx_dn_total += 1
            if tkr_is_down:
                idx_dn_match += 1
        else:
            neutral_total += 1

    total_bars = len(window) - 1

    idx_up_pct      = (idx_up_match / idx_up_total * 100) if idx_up_total > 0 else 0.0
    idx_up_miss_pct = 100.0 - idx_up_pct
    idx_dn_pct      = (idx_dn_match / idx_dn_total * 100) if idx_dn_total > 0 else 0.0
    idx_dn_miss_pct = 100.0 - idx_dn_pct

    return {
        "ticker":           ticker.upper(),
        "index_code":       index_code,
        "total_bars":       total_bars,
        "atr14":            round(atr14, 4),
        "atr_pct":          round(atr_pct, 2),
        "last_close":       round(last_close, 0),
        "tkr_threshold":    round(tkr_threshold, 2),

        "idx_up_total":     idx_up_total,
        "idx_up_match":     idx_up_match,
        "idx_up_pct":       round(idx_up_pct, 1),
        "idx_up_miss_pct":  round(idx_up_miss_pct, 1),

        "idx_dn_total":     idx_dn_total,
        "idx_dn_match":     idx_dn_match,
        "idx_dn_pct":       round(idx_dn_pct, 1),
        "idx_dn_miss_pct":  round(idx_dn_miss_pct, 1),

        "neutral_total":    neutral_total,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Formatter
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_wti(r: dict) -> str:
    t   = r["ticker"]
    idx = r["index_code"]

    idx_up_miss = r["idx_up_total"] - r["idx_up_match"]
    idx_dn_miss = r["idx_dn_total"] - r["idx_dn_match"]

    # Kesimpulan
    up  = r["idx_up_pct"]
    dn  = r["idx_dn_pct"]
    if up >= 70 and dn >= 70:
        verdict = "⭐ Sangat korelasi positif"
    elif up >= 60 and dn >= 60:
        verdict = "✅ Korelasi positif"
    elif up <= 30 and dn <= 30:
        verdict = "🛡️ Defensif / anti-korelasi"
    elif up >= 60 and dn < 50:
        verdict = "📈 Ikut naik tapi tidak ikut turun"
    elif up < 50 and dn >= 60:
        verdict = "📉 Ikut turun tapi tidak ikut naik"
    else:
        verdict = "➡️ Korelasi lemah / netral"

    lines = [
        f"📊 <b>WTI — {t} vs {idx}</b>",
        f"<code>Window : {r['total_bars']} hari bursa terakhir</code>",
        f"<code>Threshold {t:<8}: {r['tkr_threshold']:.2f}%  "
        f"(ATR14={r['atr_pct']:.2f}% | close={r['last_close']:,.0f})</code>",
        f"<code>Threshold {idx:<8}: {IDX_THRESHOLD:.1f}%  (fix)</code>",
        "",
        f"🟢 <b>{idx} Naik</b>  →  <b>{r['idx_up_total']}</b> hari",
        f"   ✅ {t} ikut naik  : <b>{up:.1f}%</b>  ({r['idx_up_match']} hari)",
        f"   ❌ {t} tidak naik : {r['idx_up_miss_pct']:.1f}%  ({idx_up_miss} hari)",
        "",
        f"🔴 <b>{idx} Turun</b> →  <b>{r['idx_dn_total']}</b> hari",
        f"   ✅ {t} ikut turun  : <b>{dn:.1f}%</b>  ({r['idx_dn_match']} hari)",
        f"   ❌ {t} tidak turun : {r['idx_dn_miss_pct']:.1f}%  ({idx_dn_miss} hari)",
        "",
        f"⚪ <b>Netral</b> (indeks flat)  : {r['neutral_total']} hari",
        "",
        f"<b>Kesimpulan:</b> {verdict}",
    ]

    return "\n".join(lines)


def _fmt_error(ticker: str, index_code: str, reason: str) -> str:
    return (
        f"❌ <b>WTI — {ticker.upper()} vs {index_code.upper()}</b>\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Telegram handler
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_wti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /wti TICKER [INDEX]

    Contoh:
        /wti BBCA               → vs COMPOSITE
        /wti BBCA LQ45          → vs LQ45
        /wti BBCA IDXFINANCE    → vs IDXFINANCE
    """
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    args = context.args

    if not args:
        valid_sample = ", ".join(sorted(VALID_INDICES)[:10])
        await update.message.reply_text(
            "⚠️ <b>Penggunaan:</b>\n"
            "  <code>/wti TICKER</code>          → vs COMPOSITE\n"
            "  <code>/wti TICKER INDEX</code>    → vs indeks pilihan\n\n"
            f"<b>Contoh:</b>\n"
            "  <code>/wti BBCA</code>\n"
            "  <code>/wti BBCA LQ45</code>\n"
            "  <code>/wti TLKM IDXFINANCE</code>\n\n"
            f"<b>Indeks tersedia (sebagian):</b>\n"
            f"<code>{valid_sample}, ...</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    ticker     = args[0].upper()
    index_code = args[1].upper() if len(args) >= 2 else DEFAULT_INDEX

    # Validasi indeks
    if index_code not in VALID_INDICES:
        # Coba cari di cache (mungkin ada indeks tambahan)
        if index_code not in _INDEX_CACHE:
            await update.message.reply_text(
                f"❌ Indeks <code>{index_code}</code> tidak dikenali.\n\n"
                f"Indeks yang tersedia:\n"
                f"<code>{', '.join(sorted(VALID_INDICES))}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

    # Cek cache indeks
    if not _INDEX_CACHE.get(index_code):
        await update.message.reply_text(
            _fmt_error(ticker, index_code,
                       f"Data indeks <code>{index_code}</code> belum tersedia di cache.\n"
                       "Minta admin jalankan reload terlebih dahulu."),
            parse_mode=ParseMode.HTML,
        )
        return

    msg = await update.message.reply_text(
        f"⏳ Menghitung <b>{ticker}</b> vs <b>{index_code}</b>…",
        parse_mode=ParseMode.HTML,
    )

    result = await asyncio.get_event_loop().run_in_executor(
        None, calculate_wti, ticker, index_code, STOCK_JSON_DIR
    )

    if result is None:
        await msg.edit_text(
            _fmt_error(
                ticker, index_code,
                f"Data tidak cukup untuk <b>{ticker}</b>.\n"
                "Pastikan ticker valid dan data JSON saham sudah tersedia.",
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    await msg.edit_text(_fmt_wti(result), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════════════

def register_wti_handler(app) -> None:
    app.add_handler(CommandHandler("wtii", cmd_wti))
