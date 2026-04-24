"""
repo_command.py — Handler /repo TICKER

Menampilkan data laporan tahunan (annual report) dari file Excel
di folder /home/ec2-user/database/repo/

Jika data belum tersedia, tampilkan pesan menunggu laporan tahunan.

Usage:
    /repo BBCA
    /repo TLKM
"""

import os
import glob
import logging

import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user

logger = logging.getLogger(__name__)

REPO_FOLDER = "/home/ec2-user/database/repo"

NO_DATA_MSG = (
    "📭 Data belum ditemukan, saya sedang menunggu laporan tahunan "
    "dari sekuritas dirilis."
)


# ══════════════════════════════════════════════════════════════════════════════
#  Helper: baca & cari data
# ══════════════════════════════════════════════════════════════════════════════

def _load_repo_df() -> pd.DataFrame | None:
    """Baca semua file xlsx di REPO_FOLDER, gabung jadi satu DataFrame."""
    if not os.path.exists(REPO_FOLDER):
        logger.warning(f"[REPO] Folder tidak ditemukan: {REPO_FOLDER}")
        return None

    excel_files = sorted(
        glob.glob(os.path.join(REPO_FOLDER, "*.xlsx")) +
        glob.glob(os.path.join(REPO_FOLDER, "*.xls")),
        reverse=True,
    )

    if not excel_files:
        logger.warning("[REPO] Tidak ada file Excel di folder repo.")
        return None

    frames = []
    for fp in excel_files:
        try:
            df = pd.read_excel(fp)
            frames.append(df)
        except Exception as e:
            logger.error(f"[REPO] Gagal baca {fp}: {e}")

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    return combined


def _find_ticker_col(df: pd.DataFrame) -> str | None:
    """Cari nama kolom yang berisi kode saham."""
    candidates = [
        "Kode Saham", "Kode", "Ticker", "KODE", "TICKER",
        "kode_saham", "kode", "ticker", "stock_code", "STOCK_CODE",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    # fallback: kolom pertama yang nilai-nilainya pendek (≤6 karakter)
    for c in df.columns:
        sample = df[c].dropna().astype(str)
        if len(sample) and sample.str.len().median() <= 6:
            return c
    return None


def _format_value(val) -> str:
    """Format nilai numerik agar lebih mudah dibaca."""
    if pd.isna(val):
        return "-"
    if isinstance(val, float):
        if val >= 1e12:
            return f"Rp {val/1e12:.2f}T"
        if val >= 1e9:
            return f"Rp {val/1e9:.2f}B"
        if val >= 1e6:
            return f"Rp {val/1e6:.2f}M"
        # persentase atau angka kecil
        return f"{val:,.2f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _build_reply(ticker: str, row: pd.Series) -> str:
    """Bangun teks reply dari satu baris data."""
    lines = [f"📋 <b>Laporan Tahunan — {ticker.upper()}</b>\n"]
    for col, val in row.items():
        # Skip kolom kode saham itu sendiri
        if str(val).upper() == ticker.upper():
            continue
        formatted = _format_value(val)
        if formatted == "-":
            continue
        lines.append(f"• <b>{col}</b>: {formatted}")
    if len(lines) == 1:
        return NO_DATA_MSG
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  Telegram handler
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler untuk command /repo TICKER

    Contoh:
        /repo BBCA
        /repo TLKM
    """
    # ── Auth guard ──
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    # ── Validasi argumen ──
    if not context.args:
        await update.message.reply_text(
            "⚠️ Gunakan: <code>/repo KODE</code>\n"
            "Contoh: <code>/repo BBCA</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    ticker = context.args[0].upper().strip()
    msg    = await update.message.reply_text(
        f"⏳ Mencari data laporan tahunan <b>{ticker}</b>…",
        parse_mode=ParseMode.HTML,
    )

    try:
        df = _load_repo_df()

        # Tidak ada file sama sekali
        if df is None or df.empty:
            await msg.edit_text(NO_DATA_MSG)
            return

        ticker_col = _find_ticker_col(df)

        # Tidak bisa deteksi kolom kode saham
        if ticker_col is None:
            logger.error("[REPO] Tidak bisa mendeteksi kolom kode saham.")
            await msg.edit_text(NO_DATA_MSG)
            return

        # Filter baris untuk ticker yang diminta
        mask  = df[ticker_col].astype(str).str.upper() == ticker
        subset = df[mask]

        if subset.empty:
            await msg.edit_text(NO_DATA_MSG)
            return

        # Ambil baris terbaru (baris pertama setelah sort descending jika ada kolom tahun)
        row = subset.iloc[0]
        reply = _build_reply(ticker, row)

        await msg.edit_text(reply, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"[REPO] Error {ticker}: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ Gagal memuat data untuk <b>{ticker}</b>.\n"
            f"<code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════════════

def register_repo_handler(app) -> None:
    """Daftarkan handler /repo ke Application. Panggil dari main.py."""
    app.add_handler(CommandHandler("repo", cmd_repo))
