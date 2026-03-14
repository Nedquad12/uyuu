"""
tight_command.py — Handler Telegram untuk /vt dan /t

/vt  → daftar saham Very Tight (jarak ke MA3/5/10/20 semua < 5%)
/t   → daftar saham Tight (jarak ke MA3/5/10/20 antara 5%–15%)

Scan dilakukan terhadap semua ticker yang tersedia di JSON_DIR.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from indicators.loader import build_stock_df, list_available_tickers
from indicators.tight import _get_tight_bucket, _calc_mas, _pct_distance, MA_PERIODS

logger = logging.getLogger(__name__)

# Di-set dari main.py saat startup
JSON_DIR = "/home/ec2-user/database/json"


# ── Scanner ────────────────────────────────────────────────────────────────────

def _scan_all_tight(json_dir: str) -> tuple[list[dict], list[dict]]:
    """
    Scan semua ticker, kembalikan (vt_list, t_list).
    Masing-masing diurutkan berdasarkan value (close × volume) descending.
    """
    tickers = list_available_tickers(json_dir)
    vt_list = []
    t_list  = []

    for ticker in tickers:
        try:
            df = build_stock_df(ticker, json_dir, max_days=30)
            if df is None or len(df) < max(MA_PERIODS):
                continue

            bucket = _get_tight_bucket(df)
            if bucket is None:
                continue

            close  = float(df["close"].iloc[-1])
            volume = float(df["volume"].iloc[-1])
            value  = (close * volume) / 1_000_000_000   # miliar Rupiah

            mas      = _calc_mas(df)
            max_dist = max(_pct_distance(close, mas[p]) for p in MA_PERIODS)

            entry = {
                "ticker":   ticker,
                "close":    close,
                "ma20":     mas[20],
                "volume":   volume,
                "value":    value,
                "max_dist": round(max_dist, 2),
            }

            if bucket == "VT":
                vt_list.append(entry)
            else:
                t_list.append(entry)

        except Exception as e:
            logger.error(f"[{ticker}] tight scan error: {e}")

    vt_list.sort(key=lambda x: x["value"], reverse=True)
    t_list.sort(key=lambda x: x["value"], reverse=True)

    return vt_list, t_list


# ── Formatter ──────────────────────────────────────────────────────────────────

def _format_table(title: str, results: list[dict]) -> list[str]:
    """
    Kembalikan list string (masing-masing siap dikirim sebagai 1 pesan Telegram).
    Dipecah per 30 baris agar tidak melebihi batas 4096 karakter.
    """
    if not results:
        return [f"```\n{title}\n\nTidak ada saham yang memenuhi kriteria.\n```"]

    header = (
        f"{title}\n\n"
        f"{'Ticker':<6}  {'Close':>8}  {'MA20':>8}  {'Dist':>6}  {'Val(B)':>7}\n"
        f"{'─' * 44}\n"
    )

    chunks = []
    chunk_lines = []
    total = len(results)

    for i, s in enumerate(results):
        line = (
            f"{s['ticker']:<6}  {s['close']:>8,.0f}  {s['ma20']:>8,.0f}"
            f"  {s['max_dist']:>5.2f}%  {s['value']:>6.1f}B\n"
        )
        chunk_lines.append(line)

        # Kirim per 30 baris atau di akhir
        if len(chunk_lines) == 30 or i == total - 1:
            footer = (
                f"{'─' * 44}\n"
                f"Total: {total} saham  |  Dist=jarak close ke MA terjauh  |  Val=miliar Rp"
            ) if i == total - 1 else f"... (lanjut)"

            msg = "```\n" + header + "".join(chunk_lines) + footer + "\n```"
            chunks.append(msg)
            chunk_lines = []
            # Header hanya di chunk pertama
            header = f"(lanjutan {title})\n{'─' * 44}\n"

    return chunks


# ── Handlers ───────────────────────────────────────────────────────────────────

async def cmd_vt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/vt — daftar saham Very Tight"""
    msg = await update.message.reply_text("⏳ Scanning saham Very Tight…")

    vt_list, _ = await asyncio.get_event_loop().run_in_executor(
        None, _scan_all_tight, JSON_DIR
    )

    chunks = _format_table("🔥 Very Tight Stocks", vt_list)
    await msg.delete()
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_t(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/t — daftar saham Tight"""
    msg = await update.message.reply_text("⏳ Scanning saham Tight…")

    _, t_list = await asyncio.get_event_loop().run_in_executor(
        None, _scan_all_tight, JSON_DIR
    )

    chunks = _format_table("✨ Tight Stocks", t_list)
    await msg.delete()
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)


# ── Registration helper ────────────────────────────────────────────────────────

def register_tight_handlers(app, json_dir: str = JSON_DIR):
    """
    Panggil dari main.py:
        from tight_command import register_tight_handlers
        register_tight_handlers(app, json_dir=OUTPUT_DIR)
    """
    global JSON_DIR
    JSON_DIR = json_dir

    app.add_handler(CommandHandler("vt", cmd_vt))
    app.add_handler(CommandHandler("t",  cmd_t))
