from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import logging
from imporh import *
import sys
sys.path.append("/home/ec2-user/package/machine")
from tight_tracker import tight_tracker

logger = logging.getLogger(__name__)

@is_authorized_user
@spy
@vip
async def vt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /vt command - very tight stocks"""
    await update.message.reply_text(
        "🔍 *Mencari saham Very Tight...*\n"
        "(Harga > semua MA)",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        results = tight_tracker.find_very_tight_stocks()
        message = tight_tracker.format_very_tight_results(results)
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in vt_command: {e}")
        await update.message.reply_text(
            "❌ Terjadi kesalahan saat menganalisis data. Silakan coba lagi.",
            parse_mode=ParseMode.MARKDOWN
        )

@is_authorized_user
@spy
@vip
async def t_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /t command - tight stocks"""
    await update.message.reply_text(
        "🔍 *Mencari saham Tight...*\n"
        "(Harga > semua MA)",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        results = tight_tracker.find_tight_stocks()
        message = tight_tracker.format_tight_results(results)
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in t_command: {e}")
        await update.message.reply_text(
            "❌ Terjadi kesalahan saat menganalisis data. Silakan coba lagi.",
            parse_mode=ParseMode.MARKDOWN
        )
