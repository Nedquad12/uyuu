
from imporh import *
from cache import clear_cache, preload_cache
from utama import TelegramStockDataViewer

viewer = TelegramStockDataViewer() 

@is_authorized_user
@spy
@vip
@with_queue_control
async def reload_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        clear_cache()
        preload_cache()
        await update.message.reply_text("♻️ Cache dihapus & semua file Excel sudah dibaca ulang ke cache ✅")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal reload cache: {e}")