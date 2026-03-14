import os
import sys
import glob
import logging
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from excel_reader import get_excel_files, excel_to_json
from admin.auth import load_roles, is_authorized_user, is_vip_user
from admin.admin_command import get_admin_conversation_handler
from user_info import get_id_pengguna

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
    """User boleh pakai bot jika punya role whitelist atau vip."""
    return is_authorized_user(user_id) or is_vip_user(user_id)


# ── Logic reload ───────────────────────────────────────────────────────────────

def _delete_all_json() -> int:
    files = glob.glob(os.path.join(OUTPUT_DIR, "*.json"))
    for f in files:
        os.remove(f)
    return len(files)


def _load_all_excel() -> tuple[int, int, list[str]]:
    excel_files = get_excel_files(EXCEL_DIR)
    if not excel_files:
        return 0, 0, []
    errors  = []
    success = 0
    for fi in excel_files:
        result = excel_to_json(fi, OUTPUT_DIR)
        if result:
            success += 1
        else:
            errors.append(fi["filename"])
    return success, len(excel_files), errors


def do_reload() -> str:
    ensure_output_dir()
    deleted = _delete_all_json()
    success, total, errors = _load_all_excel()
    lines = [
        "🔄 *RELOAD SELESAI*",
        f"🗑 {deleted} file JSON dihapus",
        f"✅ {success}/{total} file XLSX dikonversi",
    ]
    if errors:
        lines.append("❌ Gagal: " + ", ".join(errors))
    return "\n".join(lines)


# ── Logic skor ─────────────────────────────────────────────────────────────────

from scorer import do_skor as _do_skor

def do_skor(ticker: str) -> str:
    return _do_skor(ticker, json_dir=OUTPUT_DIR)


# ── Handler Telegram ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    await update.message.reply_text(
        "👋 *Bot Indikator Saham IDX*\n\n"
        "Perintah:\n"
        "  `/skor BBCA` — skor indikator saham\n"
        "  `/help` — daftar perintah",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    await update.message.reply_text(
        "📋 *Daftar Perintah*\n\n"
        "`/skor XXXX` — hitung skor semua indikator\n"
        "contoh: `/skor BBCA`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hanya bisa dipanggil dari dalam sesi admin (dipanggil oleh admin_command.py)."""
    # Perintah /4 langsung di chat biasa → tolak semua
    # Reload hanya bisa lewat panel /admin setelah login
    await update.message.reply_text(
        "⛔ Gunakan `/admin` untuk login terlebih dahulu, lalu ketik `reload`.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_skor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Gunakan: `/skor KODE`\nContoh: `/skor BBCA`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    ticker      = context.args[0].upper()
    msg         = await update.message.reply_text(f"⏳ Menghitung skor {ticker}…")
    result_text = await asyncio.get_event_loop().run_in_executor(None, do_skor, ticker)
    await msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if BOT_TOKEN == "ISI_TOKEN_BOT_KAMU_DI_SINI":
        print("❌ BOT_TOKEN belum diisi!")
        print("   Edit main.py atau: export BOT_TOKEN='123456:ABC...'")
        sys.exit(1)

    # Muat roles dari user_roles.json saat bot start
    load_roles()
    logger.info("User roles dimuat.")

    # Muat data XLSX awal
    ensure_output_dir()
    logger.info("Memuat data awal…")
    _load_all_excel()

    app = Application.builder().token(BOT_TOKEN).build()

    # Handler biasa
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("skor",  cmd_skor))
    app.add_handler(CommandHandler("4",     cmd_reload))
    app.add_handler(CommandHandler("id",    get_id_pengguna))

    # ConversationHandler untuk panel admin (/admin login → menu)
    app.add_handler(get_admin_conversation_handler())

    logger.info("Bot berjalan…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
