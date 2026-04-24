"""
ma_command.py — Handler /ma, /am, /lm

/ma   → Pilih MA (20/50/100/200), tampilkan saham yang dekat (≤3.5%) dari MA tsb
/am   → All MA: saham yang di ATAS semua MA (20/50/100/200), jarak maks 4% dari harga
/lm   → Low MA: saham yang di BAWAH semua MA (20/50/100/200), jarak maks 4% dari harga

Cache dibangun saat startup / reload via build_ma_screener_cache().

Catatan periode MA:
  Proyek ini menggunakan MA20, MA60, MA120, MA200 (bukan 50/100).
  Namun user minta bubble 20, 50, 100, 200 → kita map:
    20  → MA20
    50  → MA60   (closest equivalent)
    100 → MA120
    200 → MA200
"""

import os
import sys
import logging
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user
from indicators.loader import build_stock_df

logger = logging.getLogger(__name__)

JSON_DIR = "/home/ec2-user/database/json"

# ── Mapping label bubble → periode MA aktual ───────────────────────────────────
MA_LABEL_TO_PERIOD = {
    20:  20,
    50:  60,
    100: 120,
    200: 200,
}
MA_LABELS = [20, 50, 100, 200]   # label yang ditampilkan ke user

# ── Threshold jarak ────────────────────────────────────────────────────────────
THRESHOLD_MA   = 3.5   # /ma  : ≤ 3.5% dari MA tertentu (atas atau bawah)
THRESHOLD_AM   = 4.0   # /am  : semua MA, harga harus di atas, jarak ≤ 4%
THRESHOLD_LM   = 4.0   # /lm  : semua MA, harga harus di bawah, jarak ≤ 4%

# ── Cache ──────────────────────────────────────────────────────────────────────
# Struktur:
#   _MA_CACHE[label] = list of (kode, price, ma_val, diff_pct, value)   → untuk /ma
#                      value = volume * harga (dipakai untuk sort)
#   _AM_CACHE        = list of (kode, price, mas_dict, diffs, value)    → untuk /am
#   _LM_CACHE        = list of (kode, price, mas_dict, diffs, value)    → untuk /lm

_MA_CACHE: dict[int, list] = {k: [] for k in MA_LABELS}
_AM_CACHE: list = []
_LM_CACHE: list = []
_CACHE_TIME: datetime | None = None


# ── Auth ───────────────────────────────────────────────────────────────────────

def _is_allowed(user_id: int) -> bool:
    return is_authorized_user(user_id) or is_vip_user(user_id)


# ── Scanner ────────────────────────────────────────────────────────────────────

def _scan_all_stocks(json_dir: str = JSON_DIR) -> None:
    """
    Scan semua ticker dari file JSON terbaru.
    Hitung MA dan isi _MA_CACHE, _AM_CACHE, _LM_CACHE.
    """
    global _MA_CACHE, _AM_CACHE, _LM_CACHE, _CACHE_TIME

    if not os.path.exists(json_dir):
        logger.warning("[MA] JSON dir tidak ditemukan: %s", json_dir)
        return

    # Ambil semua ticker unik dari file JSON terbaru
    import glob, json

    json_files = sorted(glob.glob(os.path.join(json_dir, "*.json")), reverse=True)
    if not json_files:
        logger.warning("[MA] Tidak ada file JSON di: %s", json_dir)
        return

    # Kumpulkan ticker dari file terbaru
    tickers: set[str] = set()
    try:
        with open(json_files[0], encoding="utf-8") as f:
            data = json.load(f)
        for row in data:
            kode = row.get("Kode Saham") or row.get("kode") or row.get("code")
            if kode:
                tickers.add(str(kode).strip().upper())
    except Exception as e:
        logger.error("[MA] Gagal baca ticker dari JSON: %s", e)
        return

    if not tickers:
        logger.warning("[MA] Tidak ada ticker ditemukan.")
        return

    logger.info("[MA] Scan %d ticker…", len(tickers))

    new_ma_cache: dict[int, list] = {k: [] for k in MA_LABELS}
    new_am_cache: list = []
    new_lm_cache: list = []

    for kode in sorted(tickers):
        try:
            df = build_stock_df(kode, json_dir, max_days=220)
            if df is None or df.empty:
                continue

            price  = float(df["close"].iloc[-1])
            closes = df["close"]

            # Volume terbaru & value (volume × harga)
            volume = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
            value  = volume * price   # dipakai sebagai sort key

            # Hitung semua MA
            mas: dict[int, float | None] = {}
            for label in MA_LABELS:
                period = MA_LABEL_TO_PERIOD[label]
                if len(closes) >= period:
                    mas[label] = float(closes.tail(period).mean())
                else:
                    mas[label] = None

            # ── /ma cache: cek tiap MA ─────────────────────────────────────
            for label in MA_LABELS:
                ma_val = mas[label]
                if ma_val is None:
                    continue
                diff_pct = (price - ma_val) / ma_val * 100
                if abs(diff_pct) <= THRESHOLD_MA:
                    new_ma_cache[label].append((kode, price, ma_val, diff_pct, value))

            # ── /am cache: harga di ATAS semua MA, jarak ≤ 4% ────────────
            if all(mas[l] is not None for l in MA_LABELS):
                diffs = {
                    l: (price - mas[l]) / mas[l] * 100
                    for l in MA_LABELS
                }
                if all(diffs[l] > 0 for l in MA_LABELS):
                    max_diff = max(diffs[l] for l in MA_LABELS)
                    if max_diff <= THRESHOLD_AM:
                        new_am_cache.append((kode, price, {l: mas[l] for l in MA_LABELS}, diffs, value))

            # ── /lm cache: harga di BAWAH semua MA, jarak ≤ 4% ──────────
            if all(mas[l] is not None for l in MA_LABELS):
                diffs = {
                    l: (price - mas[l]) / mas[l] * 100
                    for l in MA_LABELS
                }
                if all(diffs[l] < 0 for l in MA_LABELS):
                    max_diff = min(diffs[l] for l in MA_LABELS)  # paling negatif
                    if abs(max_diff) <= THRESHOLD_LM:
                        new_lm_cache.append((kode, price, {l: mas[l] for l in MA_LABELS}, diffs, value))

        except Exception as e:
            logger.debug("[MA] Skip %s: %s", kode, e)
            continue

    # Sort: /ma → value (volume×harga) terbesar di atas
    for label in MA_LABELS:
        new_ma_cache[label].sort(key=lambda x: x[4], reverse=True)

    # Sort: /am → value terbesar di atas
    new_am_cache.sort(key=lambda x: x[4], reverse=True)

    # Sort: /lm → value terbesar di atas
    new_lm_cache.sort(key=lambda x: x[4], reverse=True)

    _MA_CACHE  = new_ma_cache
    _AM_CACHE  = new_am_cache
    _LM_CACHE  = new_lm_cache
    _CACHE_TIME = datetime.now()

    logger.info(
        "[MA] Cache selesai — MA20=%d MA50=%d MA100=%d MA200=%d | AM=%d | LM=%d",
        len(_MA_CACHE[20]), len(_MA_CACHE[50]),
        len(_MA_CACHE[100]), len(_MA_CACHE[200]),
        len(_AM_CACHE), len(_LM_CACHE),
    )


# ── Public builder (dipanggil dari main.py) ───────────────────────────────────

def build_ma_screener_cache(json_dir: str = JSON_DIR) -> str:
    """
    Build cache MA screener. Dipanggil saat startup dan reload.
    Return string ringkasan.
    """
    _scan_all_stocks(json_dir)
    return (
        f"📊 MA cache: "
        f"MA20={len(_MA_CACHE[20])} "
        f"MA50={len(_MA_CACHE[50])} "
        f"MA100={len(_MA_CACHE[100])} "
        f"MA200={len(_MA_CACHE[200])} | "
        f"AM={len(_AM_CACHE)} LM={len(_LM_CACHE)} ticker"
    )


# ── Formatter ──────────────────────────────────────────────────────────────────

def _cache_time_str() -> str:
    if _CACHE_TIME:
        return _CACHE_TIME.strftime("%d/%m/%Y %H:%M")
    return "belum tersedia"


def _fmt_ma_list(items: list, label: int) -> str:
    """Format hasil /ma untuk MA tertentu — pakai HTML."""
    period = MA_LABEL_TO_PERIOD[label]
    if not items:
        return f"Tidak ada saham dalam jarak {THRESHOLD_MA}% dari MA{label} (periode {period})."

    lines = [
        f"📊 SAHAM DEKAT MA{label} (periode {period}) — maks ±{THRESHOLD_MA}%",
        f"⏰ Cache: {_cache_time_str()}",
        f"{'='*36}",
        f"{'Kode':<6} {'MA'+str(label):>8} {'Diff%':>8} {'Pos':>4}",
        f"{'-'*36}",
    ]
    for kode, price, ma_val, diff_pct, value in items:
        pos = "▲" if diff_pct > 0 else "▼"
        lines.append(f"{kode:<6} {ma_val:>8,.0f} {diff_pct:>+7.2f}% {pos:>4}")
    lines.append(f"{'='*36}")
    lines.append(f"Total: {len(items)} saham")
    return "<pre>" + "\n".join(lines) + "</pre>"


def _fmt_am_list(items: list) -> str:
    """Format hasil /am — pakai HTML."""
    if not items:
        return f"Tidak ada saham di atas semua MA (20/50/100/200) dengan jarak ≤{THRESHOLD_AM}%."

    lines = [
        f"💚 ALL MA ATAS — Harga di atas MA20/50/100/200 (maks {THRESHOLD_AM}%)",
        f"⏰ Cache: {_cache_time_str()}",
        f"{'='*50}",
        f"{'Kode':<6} {'MA20%':>7} {'MA50%':>7} {'MA100%':>8} {'MA200%':>8}",
        f"{'-'*50}",
    ]
    for kode, price, mas, diffs, value in items:
        lines.append(
            f"{kode:<6} "
            f"{diffs[20]:>+6.2f}% "
            f"{diffs[50]:>+6.2f}% "
            f"{diffs[100]:>+7.2f}% "
            f"{diffs[200]:>+7.2f}%"
        )
    lines.append(f"{'='*50}")
    lines.append(f"Total: {len(items)} saham")
    return "<pre>" + "\n".join(lines) + "</pre>"


def _fmt_lm_list(items: list) -> str:
    """Format hasil /lm — pakai HTML."""
    if not items:
        return f"Tidak ada saham di bawah semua MA (20/50/100/200) dengan jarak ≤{THRESHOLD_LM}%."

    lines = [
        f"🔴 ALL MA BAWAH — Harga di bawah MA20/50/100/200 (maks {THRESHOLD_LM}%)",
        f"⏰ Cache: {_cache_time_str()}",
        f"{'='*50}",
        f"{'Kode':<6} {'MA20%':>7} {'MA50%':>7} {'MA100%':>8} {'MA200%':>8}",
        f"{'-'*50}",
    ]
    for kode, price, mas, diffs, value in items:
        lines.append(
            f"{kode:<6} "
            f"{diffs[20]:>+6.2f}% "
            f"{diffs[50]:>+6.2f}% "
            f"{diffs[100]:>+7.2f}% "
            f"{diffs[200]:>+7.2f}%"
        )
    lines.append(f"{'='*50}")
    lines.append(f"Total: {len(items)} saham")
    return "<pre>" + "\n".join(lines) + "</pre>"


# ── Handlers ───────────────────────────────────────────────────────────────────

async def cmd_ma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ma — Pilih periode MA, tampilkan saham yang dekat (±3.5%)."""
    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    if not _CACHE_TIME:
        await update.message.reply_text("⚠️ Cache belum tersedia. Tunggu reload selesai.")
        return

    keyboard = [
        [
            InlineKeyboardButton("MA 20",  callback_data="ma_20"),
            InlineKeyboardButton("MA 50",  callback_data="ma_50"),
        ],
        [
            InlineKeyboardButton("MA 100", callback_data="ma_100"),
            InlineKeyboardButton("MA 200", callback_data="ma_200"),
        ],
    ]

    counts = {l: len(_MA_CACHE[l]) for l in MA_LABELS}
    await update.message.reply_text(
        f"📊 <b>Moving Average Screener</b>\n\n"
        f"Pilih periode MA (±{THRESHOLD_MA}% dari MA):\n\n"
        f"• MA20  → {counts[20]} saham\n"
        f"• MA50  → {counts[50]} saham\n"
        f"• MA100 → {counts[100]} saham\n"
        f"• MA200 → {counts[200]} saham\n\n"
        f"⏰ Cache: {_cache_time_str()}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )

async def ma_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        label = int(query.data.replace("ma_", ""))
    except ValueError:
        await query.edit_message_text("❌ Pilihan tidak valid.")
        return

    items = _MA_CACHE.get(label, [])
    msg   = _fmt_ma_list(items, label)

    if len(msg) <= 4000:
        keyboard = [[InlineKeyboardButton("« Kembali", callback_data="ma_back")]]
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.edit_message_text("📊 Mengirim hasil…")
        # Split per baris, wrap tiap chunk dalam <pre>
        inner = msg.replace("<pre>", "").replace("</pre>", "")
        lines = inner.split("\n")
        chunk: list[str] = []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 3500:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="<pre>" + "\n".join(chunk) + "</pre>",
                    parse_mode=ParseMode.HTML,
                )
                await asyncio.sleep(0.3)
                chunk = []
        if chunk:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="<pre>" + "\n".join(chunk) + "</pre>",
                parse_mode=ParseMode.HTML,
            )

async def ma_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol « Kembali ke menu /ma."""
    query = update.callback_query
    await query.answer()

    counts  = {l: len(_MA_CACHE[l]) for l in MA_LABELS}
    keyboard = [
        [
            InlineKeyboardButton("MA 20",  callback_data="ma_20"),
            InlineKeyboardButton("MA 50",  callback_data="ma_50"),
        ],
        [
            InlineKeyboardButton("MA 100", callback_data="ma_100"),
            InlineKeyboardButton("MA 200", callback_data="ma_200"),
        ],
    ]
    await query.edit_message_text(
        f"📊 <b>Moving Average Screener</b>\n\n"
        f"...",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def cmd_am(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/am — Saham di ATAS semua MA (20/50/100/200), jarak maks 4%."""
    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    if not _CACHE_TIME:
        await update.message.reply_text("⚠️ Cache belum tersedia. Tunggu reload selesai.")
        return

    msg = _fmt_am_list(_AM_CACHE)

    # Split jika terlalu panjang
    if len(msg) <= 4000:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    else:
        lines = msg.split("\n")
        chunk: list[str] = []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 3500:
                await update.message.reply_text(
                    "\n".join(chunk), parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(0.3)
                chunk = []
        if chunk:
            await update.message.reply_text(
                "\n".join(chunk), parse_mode=ParseMode.MARKDOWN
            )


async def cmd_lm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lm — Saham di BAWAH semua MA (20/50/100/200), jarak maks 4%."""
    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    if not _CACHE_TIME:
        await update.message.reply_text("⚠️ Cache belum tersedia. Tunggu reload selesai.")
        return

    msg = _fmt_lm_list(_LM_CACHE)

    if len(msg) <= 4000:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    else:
        lines = msg.split("\n")
        chunk: list[str] = []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 3500:
                await update.message.reply_text(
                    "\n".join(chunk), parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(0.3)
                chunk = []
        if chunk:
            await update.message.reply_text(
                "\n".join(chunk), parse_mode=ParseMode.MARKDOWN
            )
            
async def build_ma_screener_cache_async(json_dir: str = JSON_DIR) -> str:
    """Versi async dari build_ma_screener_cache — jalankan di executor."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _scan_all_stocks, json_dir)
    return (
        f"📊 MA cache: "
        f"MA20={len(_MA_CACHE[20])} MA50={len(_MA_CACHE[50])} "
        f"MA100={len(_MA_CACHE[100])} MA200={len(_MA_CACHE[200])} | "
        f"AM={len(_AM_CACHE)} LM={len(_LM_CACHE)} ticker"
    )


# ── Registration ───────────────────────────────────────────────────────────────

def register_ma_handlers(app, json_dir: str = JSON_DIR) -> None:
    """Daftarkan semua handler MA ke Application."""
    app.add_handler(CommandHandler("ma", cmd_ma))
    app.add_handler(CommandHandler("am", cmd_am))
    app.add_handler(CommandHandler("lm", cmd_lm))
    app.add_handler(CallbackQueryHandler(ma_callback,      pattern=r"^ma_\d+$"))
    app.add_handler(CallbackQueryHandler(ma_back_callback, pattern=r"^ma_back$"))
    logger.info("[MA] Handlers registered: /ma /am /lm")
