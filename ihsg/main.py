import os
import sys
import glob
import logging
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

from excel_reader import get_excel_files, excel_to_json
from admin.auth import load_roles, is_authorized_user, is_vip_user
from admin.admin_command import get_admin_conversation_handler
from user_info import get_id_pengguna
from ownership import create_ownership_charts, create_ownership_excel, create_flow_charts, get_top_changes
from stock_holdings import cmd_sh, callback_mode, handle_search_input
from tight_command import register_tight_handlers, build_tight_cache
from free_float import cmd_ff
from fall import register_fall_handlers, build_fall_cache
from blackrock import blackrock_significant_movements, blackrock_indonesia
from margin import margin_trading
from cache_manager import build_all_external_caches   # ← BARU

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BOT_TOKEN  = "8212869606:AAGvs-HoLJfSCQ27zHofgH8wAsp7BJnYxz0"
EXCEL_DIR  = "/home/ec2-user/database/wl"
OUTPUT_DIR = "/home/ec2-user/database/json"


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def is_allowed(user_id: int) -> bool:
    return is_authorized_user(user_id) or is_vip_user(user_id)


# ── Reload ─────────────────────────────────────────────────────────────────────

def _delete_all_json() -> int:
    files = glob.glob(os.path.join(OUTPUT_DIR, "*.json"))
    for f in files:
        os.remove(f)
    return len(files)


def _load_all_excel() -> tuple[int, int, list[str]]:
    excel_files = get_excel_files(EXCEL_DIR)
    if not excel_files:
        return 0, 0, []
    errors, success = [], 0
    for fi in excel_files:
        if excel_to_json(fi, OUTPUT_DIR):
            success += 1
        else:
            errors.append(fi["filename"])
    return success, len(excel_files), errors


def do_reload() -> str:
    ensure_output_dir()
    deleted = _delete_all_json()
    success, total, errors = _load_all_excel()

    # Build tight cache di RAM setelah JSON siap
    n_vt, n_t = build_tight_cache(json_dir=OUTPUT_DIR)
    fall_summary = build_fall_cache()

    # Build external indicator caches (MGN, BRK, OWN)   ← BARU
    ext_summary = build_all_external_caches()

    lines = [
        "🔄 *RELOAD SELESAI*",
        f"🗑 {deleted} file JSON dihapus",
        f"✅ {success}/{total} file XLSX dikonversi",
        f"📊 Tight cache: {n_vt} VT, {n_t} T",
        ext_summary,
    ]
    if errors:
        lines.append("❌ Gagal: " + ", ".join(errors))
    return "\n".join(lines)


# ── Skor ───────────────────────────────────────────────────────────────────────

from scorer import do_skor as _do_skor

def do_skor(ticker: str) -> str:
    return _do_skor(ticker, json_dir=OUTPUT_DIR)


# ── Handlers ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    await update.message.reply_text(
        "👋 *Bot Indikator Saham IDX*\n\n"
        "Perintah:\n"
        "  `/skor BBCA` — skor indikator saham\n"
        "  `/ex BBCA` — grafik kepemilikan (Lokal & Asing)\n"
        "  `/xlsx BBCA` — unduh Excel kepemilikan\n"
        "  `/help` — daftar perintah",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    await update.message.reply_text(
        "📋 *Daftar Perintah*\n\n"
        "`/skor XXXX` — skor semua indikator\n"
        "`/ex XXXX` — pie chart kepemilikan Lokal & Asing\n"
        "`/xlsx XXXX` — unduh Excel kepemilikan\n"
        "contoh: `/skor BBCA` · `/ex BBCA` · `/xlsx BBCA`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⛔ Gunakan `/admin` untuk login terlebih dahulu, lalu ketik `reload`.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_skor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Gunakan: `/skor KODE`\nContoh: `/skor BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    ticker = context.args[0].upper()
    msg    = await update.message.reply_text(f"⏳ Menghitung skor {ticker}…")
    result = await asyncio.get_event_loop().run_in_executor(None, do_skor, ticker)
    await msg.edit_text(result, parse_mode=ParseMode.MARKDOWN)


async def cmd_ex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim 2 pie chart kepemilikan: Lokal + Asing (data terbaru)."""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Gunakan: `/ex KODE`\nContoh: `/ex BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = context.args[0].upper()
    msg    = await update.message.reply_text(
        f"⏳ Memuat grafik kepemilikan *{ticker}*…", parse_mode=ParseMode.MARKDOWN
    )

    buf_local, buf_foreign = await asyncio.get_event_loop().run_in_executor(
        None, create_ownership_charts, ticker
    )

    if buf_local is None:
        await msg.edit_text(
            f"❌ Data kepemilikan *{ticker}* tidak ditemukan.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await msg.delete()

    caption_local = (
        f"🇮🇩 *Kepemilikan LOKAL — {ticker}*\n"
        "IS=Asuransi  CP=Korporat  PF=Dana Pensiun  IB=Bank  "
        "ID=Ritel  MF=Reksadana  SC=Sekuritas  FD=Foundation  OT=Lainnya"
    )
    caption_foreign = (
        f"🌏 *Kepemilikan ASING — {ticker}*\n"
        "IS=Asuransi  CP=Korporat  PF=Dana Pensiun  IB=Bank  "
        "ID=Ritel  MF=Reksadana  SC=Sekuritas  FD=Foundation  OT=Lainnya"
    )

    await update.message.reply_photo(photo=buf_local,  caption=caption_local,
                                     parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_photo(photo=buf_foreign, caption=caption_foreign,
                                     parse_mode=ParseMode.MARKDOWN)


async def cmd_xlsx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim file Excel kepemilikan (Shares + Value + Ownership %)."""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Gunakan: `/xlsx KODE`\nContoh: `/xlsx BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = context.args[0].upper()
    msg    = await update.message.reply_text(
        f"⏳ Membuat Excel *{ticker}*…", parse_mode=ParseMode.MARKDOWN
    )

    buf = await asyncio.get_event_loop().run_in_executor(
        None, create_ownership_excel, ticker
    )

    if buf is None:
        await msg.edit_text(
            f"❌ Data kepemilikan *{ticker}* tidak ditemukan.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await msg.delete()
    await update.message.reply_document(
        document=buf,
        filename=f"{ticker}_kepemilikan.xlsx",
        caption=(
            f"📊 *{ticker}* — Data Kepemilikan\n\n"
            "📋 Sheet *Shares*: data dalam lembar saham\n"
            "💰 Sheet *Value*: data dalam Rupiah (lembar × harga terbaru) + Ownership %\n\n"
            "Kategori: IS=Asuransi, CP=Korporat, PF=Dana Pensiun, IB=Bank, "
            "ID=Ritel, MF=Reksadana, SC=Sekuritas, FD=Foundation, OT=Lainnya"
        ),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_forc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /forc TICKER [N]
    N = bulan ke belakang sebagai pembanding (1–5, default 1).
    Contoh: /forc BBCA 3  → terbaru vs 3 bulan sebelumnya
    """
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Gunakan: `/forc KODE [N]`\nContoh: `/forc BBCA` atau `/forc BBCA 3`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = context.args[0].upper()
    n      = 1
    if len(context.args) >= 2:
        try:
            n = max(1, min(5, int(context.args[1])))
        except ValueError:
            pass

    msg = await update.message.reply_text(
        f"⏳ Menghitung perubahan kepemilikan *{ticker}* ({n} bulan ke belakang)…",
        parse_mode=ParseMode.MARKDOWN,
    )

    buf_local, buf_foreign = await asyncio.get_event_loop().run_in_executor(
        None, lambda: create_flow_charts(ticker, n)
    )

    if buf_local is None:
        await msg.edit_text(
            f"❌ Data *{ticker}* tidak ditemukan atau data kurang dari {n+1} bulan.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await msg.delete()

    await update.message.reply_photo(
        photo=buf_local,
        caption=f"🇮🇩 *Perubahan Kepemilikan LOKAL — {ticker}*",
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.message.reply_photo(
        photo=buf_foreign,
        caption=f"🌏 *Perubahan Kepemilikan ASING — {ticker}*",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /top — ranking perubahan kepemilikan ──────────────────────────────────────

TOP_CATEGORIES = {
    'ALL': 'Total',
    'IS':  'Asuransi',
    'CP':  'Korporat',
    'PF':  'Dana Pensiun',
    'IB':  'Bank',
    'ID':  'Ritel',
    'MF':  'Reksadana',
    'SC':  'Sekuritas',
    'FD':  'Foundation',
    'OT':  'Lainnya',
}


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: pilih Local atau Foreign."""
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    keyboard = [
        [
            InlineKeyboardButton("🇮🇩 Lokal",  callback_data="top_side_local"),
            InlineKeyboardButton("🌏 Asing",   callback_data="top_side_foreign"),
        ]
    ]
    await update.message.reply_text(
        "📊 *Top 20 Perubahan Kepemilikan*\n\nPilih jenis investor:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cb_top_side(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: pilih kategori setelah user klik Local/Foreign."""
    query = update.callback_query
    await query.answer()

    side = query.data.split("_")[2]   # 'local' atau 'foreign'
    context.user_data['top_side'] = side
    label = "🇮🇩 Lokal" if side == "local" else "🌏 Asing"

    # Buat grid tombol kategori 2 per baris
    cats   = list(TOP_CATEGORIES.items())
    rows   = []
    for i in range(0, len(cats), 2):
        row = []
        for code, name in cats[i:i+2]:
            row.append(InlineKeyboardButton(name, callback_data=f"top_cat_{side}_{code}"))
        rows.append(row)

    await query.edit_message_text(
        f"📊 *Top 20 — {label}*\n\nPilih kategori:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cb_top_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: hitung & kirim 2 pesan terpisah — top 20 naik + top 20 turun."""
    query = update.callback_query
    await query.answer()

    parts    = query.data.split("_")   # top_cat_local_IS
    side     = parts[2]
    category = parts[3]

    side_label = "🇮🇩 Lokal" if side == "local" else "🌏 Asing"
    cat_label  = TOP_CATEGORIES.get(category, category)

    await query.edit_message_text(
        f"⏳ Menghitung top 20 {side_label} — {cat_label}…"
    )

    res = await asyncio.get_event_loop().run_in_executor(
        None, lambda: get_top_changes(side, category, top_n=20)
    )

    if res is None:
        await query.edit_message_text("❌ Data tidak cukup untuk menghitung perubahan.")
        return

    top_up, top_down = res
    header = f"_{side_label} {cat_label} — bulan terbaru vs sebelumnya_"

    def build_table(rows: list, title: str) -> str:
        lines = [
            title,
            header,
            "",
            "```",
            f"{'No':<3} {'Ticker':<6} {'Change':>9}",
            "─" * 22,
        ]
        for r in rows:
            sign = "+" if r['change_pct'] >= 0 else ""
            lines.append(
                f"{r['rank']:<3} {r['ticker']:<6} {sign}{r['change_pct']:>7.2f}%"
            )
        lines.append("```")
        return "\n".join(lines)

    # Edit pesan loading → tabel naik
    await query.edit_message_text(
        build_table(top_up, "📈 *Top 20 Kenaikan Kepemilikan*"),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Kirim pesan baru untuk tabel turun
    await query.message.reply_text(
        build_table(top_down, "📉 *Top 20 Penurunan Kepemilikan*"),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    load_roles()
    logger.info("User roles dimuat.")
    ensure_output_dir()
    logger.info("Memuat data awal…")
    _load_all_excel()
    build_tight_cache(json_dir=OUTPUT_DIR)
    build_fall_cache()

    # Build external indicator caches saat startup   ← BARU
    logger.info("Membangun external cache (MGN, BRK, OWN)…")
    build_all_external_caches()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("skor",  cmd_skor))
    app.add_handler(CommandHandler("4",     cmd_reload))
    app.add_handler(CommandHandler("id",    get_id_pengguna))
    app.add_handler(CommandHandler("ex",    cmd_ex))
    app.add_handler(CommandHandler("xlsx",  cmd_xlsx))
    app.add_handler(CommandHandler("forc",  cmd_forc))
    app.add_handler(CommandHandler("top",   cmd_top))
    app.add_handler(CommandHandler("sh",    cmd_sh))
    app.add_handler(CommandHandler("ff",    cmd_ff))
    app.add_handler(CommandHandler("bi",    blackrock_indonesia))
    app.add_handler(CommandHandler("b7",    blackrock_significant_movements))
    app.add_handler(CommandHandler("m",     margin_trading))
    register_tight_handlers(app, json_dir=OUTPUT_DIR)
    register_fall_handlers(app)
    app.add_handler(CallbackQueryHandler(cb_top_side, pattern=r"^top_side_"))
    app.add_handler(CallbackQueryHandler(cb_top_cat,  pattern=r"^top_cat_"))
    app.add_handler(CallbackQueryHandler(callback_mode, pattern="^mode_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_input))

    app.add_handler(get_admin_conversation_handler())

    logger.info("Bot berjalan…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
