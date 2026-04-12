"""
atr_command.py — Handler Telegram untuk /atr TICKER

Tampilkan ATR (Average True Range) dan ATR% untuk:
  - Hari kemarin (bar terakhir)
  - Rata-rata 7 hari terakhir

ATR periode default = 14.
ATR% = ATR / Close × 100

Cache di-build saat startup / reload via build_atr_cache().

Integrasi ke main.py:
    from atr_command import register_atr_handler, build_atr_cache

    # di do_reload() dan main():
    build_atr_cache()

    # di main():
    register_atr_handler(app)
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user, check_public_group_access
from admin.admin_command import active_admins
from indicators.loader import build_stock_df, list_available_tickers

logger = logging.getLogger(__name__)

JSON_DIR   = "/home/ec2-user/database/json"
ATR_PERIOD = 14

# ── Global cache ───────────────────────────────────────────────────────────────
# Struktur: { "BBCA": { ticker, date, atr_yday, atrpct_yday, ... }, ... }
_atr_cache: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
#  Auth guard
# ══════════════════════════════════════════════════════════════════════════════

def _is_allowed(user_id: int) -> bool:
    return is_authorized_user(user_id) or is_vip_user(user_id)


# ══════════════════════════════════════════════════════════════════════════════
#  ATR calculator
# ══════════════════════════════════════════════════════════════════════════════

def _calc_atr(df, period: int = ATR_PERIOD) -> np.ndarray:
    """Hitung ATR (Wilder smoothing) dari DataFrame high/low/close."""
    high  = df["high"].values.astype(float)
    low   = df["low"].values.astype(float)
    close = df["close"].values.astype(float)

    tr = np.zeros(len(df))
    for i in range(len(df)):
        hl = high[i] - low[i]
        if i == 0:
            tr[i] = hl
        else:
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i]  - close[i - 1])
            tr[i] = max(hl, hc, lc)

    atr = np.zeros(len(tr))
    if len(tr) < period:
        return atr

    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def _compute_atr_data(ticker: str) -> dict | None:
    """Hitung ATR satu ticker dari JSON. Return dict atau None."""
    df = build_stock_df(ticker, JSON_DIR, max_days=ATR_PERIOD + 10)
    if df is None or len(df) < ATR_PERIOD:
        return None

    atr_arr   = _calc_atr(df, ATR_PERIOD)
    valid_idx = ATR_PERIOD - 1
    last_idx  = len(df) - 1

    atr_yday    = float(atr_arr[last_idx])
    close_yday  = float(df["close"].iloc[last_idx])
    atrpct_yday = (atr_yday / close_yday * 100) if close_yday > 0 else 0.0
    date_yday   = df["date"].iloc[last_idx]

    start_7       = max(valid_idx, last_idx - 6)
    atr_7d        = atr_arr[start_7: last_idx + 1]
    close_7d      = df["close"].values[start_7: last_idx + 1].astype(float)
    atrpct_7d_arr = np.where(close_7d > 0, atr_7d / close_7d * 100, 0.0)

    return {
        "ticker":        ticker.upper(),
        "date":          date_yday,
        "close_yday":    close_yday,
        "atr_yday":      atr_yday,
        "atrpct_yday":   atrpct_yday,
        "avg_atr_7d":    float(np.mean(atr_7d)),
        "avg_atrpct_7d": float(np.mean(atrpct_7d_arr)),
        "n_days":        len(atr_7d),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Cache builder — dipanggil saat startup / reload
# ══════════════════════════════════════════════════════════════════════════════

def build_atr_cache() -> None:
    """
    Hitung ATR semua saham dari JSON dan simpan ke _atr_cache.
    Dipanggil saat startup dan do_reload().
    """
    global _atr_cache

    tickers = list_available_tickers(JSON_DIR)
    if not tickers:
        logger.warning("[ATR] Tidak ada ticker ditemukan di JSON_DIR")
        _atr_cache = {}
        return

    cache = {}
    ok, skip = 0, 0
    for ticker in tickers:
        data = _compute_atr_data(ticker)
        if data:
            cache[ticker] = data
            ok += 1
        else:
            skip += 1

    _atr_cache = cache
    logger.info(f"[ATR] Cache selesai: {ok} saham, {skip} dilewati")


# ══════════════════════════════════════════════════════════════════════════════
#  Format pesan
# ══════════════════════════════════════════════════════════════════════════════

def format_atr_message(data: dict) -> str:
    date_str = (
        data["date"].strftime("%d %b %Y")
        if hasattr(data["date"], "strftime")
        else str(data["date"])
    )
    return (
        f"📐 *ATR — {data['ticker']}*\n"
        f"_Data per {date_str}_\n\n"
        f"```\n"
        f"{'Kemarin':<22}\n"
        f"  Close     : {data['close_yday']:>12,.0f}\n"
        f"  ATR (14)  : {data['atr_yday']:>12,.2f}\n"
        f"  ATR%      : {data['atrpct_yday']:>11.2f}%\n\n"
        f"{'Rata-rata 7 Hari':<22}\n"
        f"  ATR (14)  : {data['avg_atr_7d']:>12,.2f}\n"
        f"  ATR%      : {data['avg_atrpct_7d']:>11.2f}%\n"
        f"  (n={data['n_days']} hari)\n"
        f"```"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Telegram handler
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_atr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /atr TICKER
    Tampilkan ATR dan ATR% kemarin + rata-rata 7 hari.
    """
    if not await check_public_group_access(update, active_admins):
        return

    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke fitur ini.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Gunakan: `/atr KODE`\nContoh: `/atr BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = args[0].upper().strip()

    # Lookup cache — tidak perlu executor
    data = _atr_cache.get(ticker)
    if data is None:
        await update.message.reply_text(
            f"❌ Data *{ticker}* tidak ditemukan atau data kurang dari {ATR_PERIOD} hari.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.reply_text(
        format_atr_message(data),
        parse_mode=ParseMode.MARKDOWN,
    )


def register_atr_handler(app) -> None:
    """Daftarkan handler /atr ke Application. Panggil dari main.py."""
    app.add_handler(CommandHandler("atr", cmd_atr))
