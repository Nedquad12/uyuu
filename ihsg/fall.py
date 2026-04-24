"""
fall.py — Handler /fall

Analisis Net Asing per timeframe (1D, 1W, 1M, 1Q).
Cache dibangun otomatis saat startup dan saat admin menjalankan reload.

Format file: /home/ec2-user/database/json/ddmmyy.json
             array of objects, kolom: "Kode Saham", "Foreign Net"
"""

import os
import glob
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

JSON_DIR = "/home/ec2-user/database/json"

# ── Cache di RAM ───────────────────────────────────────────────────────────────
NET_ASING_CACHE: Dict[str, Dict[str, float]] = {
    '1d': {},
    '1w': {},
    '1m': {},
    '1q': {},
}

LAST_RELOAD_TIME: datetime | None = None
LATEST_DATA_DATE: datetime | None = None   # tanggal file terbaru yang berhasil dibaca


# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_date_from_filename(filename: str) -> datetime | None:
    """Parse tanggal dari nama file format ddmmyy.json → datetime."""
    try:
        stem  = os.path.splitext(filename)[0]   # buang ekstensi
        day   = int(stem[0:2])
        month = int(stem[2:4])
        year  = int('20' + stem[4:6])
        return datetime(year, month, day)
    except Exception as e:
        logger.warning(f"[FALL] Error parsing date from '{filename}': {e}")
        return None


def _get_latest_json_file() -> tuple[str | None, datetime | None]:
    """Return (path, tanggal) file .json terbaru di JSON_DIR.
    Sort berdasarkan parsed date, bukan nama file string,
    karena ddmmyy tidak sortable secara alfabetis (311025 > 010326 secara string).
    """
    if not os.path.exists(JSON_DIR):
        return None, None
    candidates = []
    for fp in glob.glob(os.path.join(JSON_DIR, "*.json")):
        d = parse_date_from_filename(os.path.basename(fp))
        if d:
            candidates.append((fp, d))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0]


def get_json_files_in_range(start_date: datetime, end_date: datetime) -> List[str]:
    """Ambil semua file .json dalam rentang tanggal, sorted ascending."""
    if not os.path.exists(JSON_DIR):
        logger.warning(f"[FALL] JSON directory tidak ditemukan: {JSON_DIR}")
        return []

    files = []
    for filename in os.listdir(JSON_DIR):
        if not filename.endswith('.json'):
            continue
        file_date = parse_date_from_filename(filename)
        if file_date and start_date.date() <= file_date.date() <= end_date.date():
            files.append((os.path.join(JSON_DIR, filename), file_date))

    logger.info(f"[FALL] {len(files)} file dalam range "
                f"{start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")
    # Sort by parsed date (bukan string) agar akumulasi urut benar
    files.sort(key=lambda x: x[1])
    return [fp for fp, _ in files]


def load_json_file(file_path: str) -> List[Dict] | None:
    """
    Load JSON dari file.
    Format yang diharapkan: array of objects
    [ {"Kode Saham": "AADI", "Foreign Net": 1355800, ...}, ... ]
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.warning(f"[FALL] Format tidak dikenal (bukan array): {file_path}")
            return None
        return data
    except Exception as e:
        logger.warning(f"[FALL] Error loading {file_path}: {e}")
        return None


def extract_net_asing(data: List[Dict]) -> Dict[str, float]:
    """
    Ekstrak Foreign Net per kode saham dari array JSON.
    Langsung pakai kolom 'Foreign Net' yang sudah ada di file.
    """
    net_dict: Dict[str, float] = {}
    for row in data:
        kode = row.get('Kode Saham')
        if not kode or not isinstance(kode, str):
            continue
        try:
            net = float(row.get('Foreign Net', 0) or 0)
            net_dict[kode.strip()] = net
        except (ValueError, TypeError):
            continue
    return net_dict


def aggregate_net_asing(file_paths: List[str]) -> Dict[str, float]:
    """Akumulasi Foreign Net dari beberapa file JSON."""
    total_net: Dict[str, float] = {}
    for fp in file_paths:
        data = load_json_file(fp)
        if not data:
            continue
        for kode, net in extract_net_asing(data).items():
            total_net[kode] = total_net.get(kode, 0.0) + net
    return total_net


def format_number(num: float) -> str:
    """Format angka ke singkatan B/M/K."""
    abs_num = abs(num)
    if abs_num >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    if abs_num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    if abs_num >= 1_000:
        return f"{num/1_000:.2f}K"
    return f"{num:.0f}"


def get_top_bottom_net(timeframe: str) -> Tuple[List[Tuple], List[Tuple]]:
    """Return (top_20_akumulasi, top_20_dibuang) untuk timeframe tertentu."""
    net_dict = NET_ASING_CACHE.get(timeframe, {})
    if not net_dict:
        return [], []
    sorted_desc = sorted(net_dict.items(), key=lambda x: x[1], reverse=True)
    sorted_asc  = sorted(net_dict.items(), key=lambda x: x[1])
    return sorted_desc[:20], sorted_asc[:20]


# ── Build cache (dipanggil dari main.py) ──────────────────────────────────────

def build_fall_cache() -> str:
    """
    Bangun NET_ASING_CACHE untuk semua timeframe dari file JSON di JSON_DIR.

    Format file : ddmmyy.json
    Isi file    : array of objects dengan kolom 'Kode Saham' dan 'Foreign Net'

    1D  = file terbaru yang tersedia (satu hari perdagangan)
    1W  = akumulasi 7 hari ke belakang dari tanggal file terbaru
    1M  = akumulasi 30 hari ke belakang
    1Q  = akumulasi 90 hari ke belakang
    """
    global LAST_RELOAD_TIME, LATEST_DATA_DATE

    latest_file, latest_date = _get_latest_json_file()

    if not latest_file:
        logger.warning("[FALL] Tidak ada file JSON ditemukan di " + JSON_DIR)
        LAST_RELOAD_TIME = datetime.now()
        return "📡 Fall cache: tidak ada file JSON ditemukan"

    LATEST_DATA_DATE = latest_date
    today            = latest_date  # acuan dari file terbaru, bukan datetime.now()

    week_ago    = today - timedelta(days=7)
    month_ago   = today - timedelta(days=30)
    quarter_ago = today - timedelta(days=90)

    # 1D = hanya satu file terbaru
    NET_ASING_CACHE['1d'] = aggregate_net_asing([latest_file])
    NET_ASING_CACHE['1w'] = aggregate_net_asing(get_json_files_in_range(week_ago,    today))
    NET_ASING_CACHE['1m'] = aggregate_net_asing(get_json_files_in_range(month_ago,   today))
    NET_ASING_CACHE['1q'] = aggregate_net_asing(get_json_files_in_range(quarter_ago, today))

    LAST_RELOAD_TIME = datetime.now()

    date_str = today.strftime('%d/%m/%Y') if today else '?'
    summary  = (
        f"📡 Fall cache (data: {date_str}): "
        f"1D={len(NET_ASING_CACHE['1d'])} "
        f"1W={len(NET_ASING_CACHE['1w'])} "
        f"1M={len(NET_ASING_CACHE['1m'])} "
        f"1Q={len(NET_ASING_CACHE['1q'])} saham"
    )
    logger.info(summary)
    return summary


# ── Telegram Handlers ──────────────────────────────────────────────────────────

async def cmd_fall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/fall — Tampilkan pilihan timeframe net asing."""
    from admin.auth import is_authorized_user, is_vip_user
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    keyboard = [
        [
            InlineKeyboardButton("1D (Hari Ini)", callback_data="fall_1d"),
            InlineKeyboardButton("1W (Minggu)",   callback_data="fall_1w"),
        ],
        [
            InlineKeyboardButton("1M (Bulan)",    callback_data="fall_1m"),
            InlineKeyboardButton("1Q (Quarter)",  callback_data="fall_1q"),
        ],
    ]

    if LAST_RELOAD_TIME:
        date_info = (
            f"📅 Data: {LATEST_DATA_DATE.strftime('%d/%m/%Y')}\n"
            f"⏰ Cache: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M')}"
        ) if LATEST_DATA_DATE else f"⏰ Cache: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M')}"
    else:
        date_info = "⚠️ Cache belum tersedia."

    await update.message.reply_text(
        f"📊 *Analisis Net Asing*\n\n"
        f"Pilih timeframe:\n"
        f"• Top 20 Akumulasi (Terbesar)\n"
        f"• Top 20 Dibuang (Terkecil)\n\n"
        f"{date_info}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def fall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback tombol timeframe."""
    query = update.callback_query
    await query.answer()

    timeframe = query.data.replace('fall_', '')

    if not NET_ASING_CACHE.get(timeframe):
        await query.edit_message_text(
            "⚠️ Cache belum tersedia. Minta admin jalankan `reload`."
        )
        return

    top_20, bottom_20 = get_top_bottom_net(timeframe)

    if not top_20 and not bottom_20:
        await query.edit_message_text(
            f"❌ Tidak ada data untuk timeframe {timeframe.upper()}"
        )
        return

    date_str = LATEST_DATA_DATE.strftime('%d/%m/%Y') if LATEST_DATA_DATE else '-'
    tf_display = {
        '1d': f"1D — {date_str}",
        '1w': '1W (7 Hari)',
        '1m': '1M (30 Hari)',
        '1q': '1Q (90 Hari)',
    }

    msg  = f"📊 *Net Asing — {tf_display.get(timeframe, timeframe.upper())}*\n\n"

    msg += "🟢 *TOP 20 AKUMULASI (Lembar Saham)*\n"
    msg += "```\n"
    msg += f"{'No':<3} {'Kode':<6} {'Net Asing':>12}\n"
    msg += "─" * 24 + "\n"
    for idx, (kode, net) in enumerate(top_20, 1):
        msg += f"{idx:<3} {kode:<6} {format_number(net):>12}\n"
    msg += "```\n\n"

    msg += "🔴 *TOP 20 DIBUANG (Lembar Saham)*\n"
    msg += "```\n"
    msg += f"{'No':<3} {'Kode':<6} {'Net Asing':>12}\n"
    msg += "─" * 24 + "\n"
    for idx, (kode, net) in enumerate(bottom_20, 1):
        msg += f"{idx:<3} {kode:<6} {format_number(net):>12}\n"
    msg += "```"

    keyboard = [[InlineKeyboardButton("« Kembali", callback_data="fall_back")]]
    await query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def fall_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol « Kembali ke menu timeframe."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("1D (Hari Ini)", callback_data="fall_1d"),
            InlineKeyboardButton("1W (Minggu)",   callback_data="fall_1w"),
        ],
        [
            InlineKeyboardButton("1M (Bulan)",    callback_data="fall_1m"),
            InlineKeyboardButton("1Q (Quarter)",  callback_data="fall_1q"),
        ],
    ]

    if LAST_RELOAD_TIME:
        date_info = (
            f"📅 Data: {LATEST_DATA_DATE.strftime('%d/%m/%Y')}\n"
            f"⏰ Cache: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M')}"
        ) if LATEST_DATA_DATE else f"⏰ Cache: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M')}"
    else:
        date_info = "⚠️ Cache belum tersedia."

    await query.edit_message_text(
        f"📊 *Analisis Net Asing*\n\n"
        f"Pilih timeframe:\n"
        f"• Top 20 Akumulasi (Terbesar)\n"
        f"• Top 20 Dibuang (Terkecil)\n\n"
        f"{date_info}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Registration ───────────────────────────────────────────────────────────────

def register_fall_handlers(app):
    """Daftarkan handler /fall ke Application."""
    app.add_handler(CommandHandler("fall", cmd_fall))
    app.add_handler(CallbackQueryHandler(fall_callback,      pattern=r"^fall_(1d|1w|1m|1q)$"))
    app.add_handler(CallbackQueryHandler(fall_back_callback, pattern=r"^fall_back$"))
