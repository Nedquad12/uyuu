from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import logging
from imporh import *
import sys
sys.path.append("/home/ec2-user/package/machine")
from ma_tracker import ma_tracker

logger = logging.getLogger(__name__)

# Command handlers
@is_authorized_user
@spy
@vip
async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /reload command - reload data to RAM cache and recalculate MA"""
    await update.message.reply_text("🔄 *Reloading data and calculating MA...*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        ma_tracker.reload_data()
        cache_info = ma_tracker.get_cache_info()
        
        message = "✅ *Data berhasil direload dan MA dihitung!*\n\n"
        message += f"📁 Files loaded: {cache_info['files_loaded']}\n"
        message += f"📈 Stocks with MA: {cache_info['stocks_with_ma']}\n"
        message += f"💾 Total memory: {cache_info['total_memory_mb']:.1f} MB\n"
        message += f"🕒 Last reload: {cache_info['last_reload'].strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in reload_command: {e}")
        await update.message.reply_text(
            "❌ Terjadi kesalahan saat reload data. Silakan coba lagi.",
            parse_mode=ParseMode.MARKDOWN
        )

@is_authorized_user
@spy
@vip
async def cache_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /cacheinfo command - show cache information"""
    try:
        cache_info = ma_tracker.get_cache_info()
        
        message = "*Cache Information*\n\n"
        message += f"📁 Files in cache: {cache_info['files_loaded']}\n"
        message += f"📈 Stocks with MA: {cache_info['stocks_with_ma']}\n"
        message += f"📊 Total files available: {cache_info['total_files_available']}\n"
        message += f"💾 RAM usage: {cache_info['ram_usage_mb']:.1f} MB\n"
        message += f"🧠 MA cache: {cache_info['ma_cache_mb']:.1f} MB\n"
        message += f"🎯 Total memory: {cache_info['total_memory_mb']:.1f} MB\n"
        
        if cache_info['last_reload']:
            message += f"🕒 Last reload: {cache_info['last_reload'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        else:
            message += "🕒 Last reload: Never\n"
        
        # Show newest and oldest file dates
        if ma_tracker.files_info:
            newest = ma_tracker.files_info[0]['date'].strftime('%Y-%m-%d')
            oldest = ma_tracker.files_info[-1]['date'].strftime('%Y-%m-%d')
            message += f"📅 Data range: {oldest} to {newest}"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in cache_info_command: {e}")
        await update.message.reply_text(
            "❌ Terjadi kesalahan saat mengambil info cache.",
            parse_mode=ParseMode.MARKDOWN
        )

@is_authorized_user
@spy
@vip
async def ma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /ma command - show MA selection buttons"""
    keyboard = [
        [
            InlineKeyboardButton("MA20", callback_data="ma_near_20"),
            InlineKeyboardButton("MA60", callback_data="ma_near_60")
        ],
        [
            InlineKeyboardButton("MA120", callback_data="ma_near_120"),
            InlineKeyboardButton("MA200", callback_data="ma_near_200")
        ],
        [
            InlineKeyboardButton("All Near MA20", callback_data="ma_all_20"),
            InlineKeyboardButton("All Near MA60", callback_data="ma_all_60")
        ],
        [
            InlineKeyboardButton("All Near MA120", callback_data="ma_all_120"),
            InlineKeyboardButton("All Near MA200", callback_data="ma_all_200")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "*MA Tracker - Saham Dekat MA*\n\n"
        "Pilih periode MA:\n"
        "• **MA20/60/120/200**: Top 50 saham terdekat\n"
        "• **All Near**: Semua saham dalam range ±3%",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

@is_authorized_user
@spy
@vip
async def cma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /cma command - show cross MA selection buttons"""
    keyboard = [
        [
            InlineKeyboardButton("Cross MA20", callback_data="ma_cross_20"),
            InlineKeyboardButton("Cross MA60", callback_data="ma_cross_60")
        ],
        [
            InlineKeyboardButton("Cross MA120", callback_data="ma_cross_120"),
            InlineKeyboardButton("Cross MA200", callback_data="ma_cross_200")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "*Cross MA Tracker - Saham Nembus MA*\n\n"
        "Pilih periode MA untuk melihat saham yang baru saja nembus (cross) MA:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

@is_authorized_user
@spy
@vip
async def am_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /am command - above all MA"""
    await update.message.reply_text("🔍 *Mencari saham above all MA...*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        results = ma_tracker.find_above_all_ma_stocks()
        title = "Above All MA (20,60,120,200) - Max +3% dari MA tertinggi"
        
        # Format results (returns list of messages if split)
        messages = ma_tracker.format_results(results, title, show_all=True)
        
        # Send first message as reply
        await update.message.reply_text(messages[0], parse_mode=ParseMode.MARKDOWN)
        
        # Send additional messages if any
        for additional_message in messages[1:]:
            await update.message.reply_text(additional_message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in am_command: {e}")
        await update.message.reply_text(
            "❌ Terjadi kesalahan saat menganalisis data. Silakan coba lagi.",
            parse_mode=ParseMode.MARKDOWN
        )
        
@is_authorized_user
@spy
@vip
async def low_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /low command - below all MA"""
    await update.message.reply_text("🔍 *Mencari saham below all MA...*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        results = ma_tracker.find_below_all_ma_stocks()
        title = "Below All MA (20,60,120,200) - Max -6% dari MA terendah"
        
        messages = ma_tracker.format_results(results, title, show_all=True)
        
        await update.message.reply_text(messages[0], parse_mode=ParseMode.MARKDOWN)
        for additional_message in messages[1:]:
            await update.message.reply_text(additional_message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in low_command: {e}")
        await update.message.reply_text(
            "❌ Terjadi kesalahan saat menganalisis data. Silakan coba lagi.",
            parse_mode=ParseMode.MARKDOWN
        )

async def ma_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries for MA buttons"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    try:
        if callback_data.startswith("ma_near_") or callback_data.startswith("ma_all_"):
            # Near MA analysis
            parts = callback_data.split("_")
            period = int(parts[-1])
            show_all = callback_data.startswith("ma_all_")
            
            if show_all:
                await query.edit_message_text(f"🔍 *Mencari SEMUA saham dekat MA{period}...*", parse_mode=ParseMode.MARKDOWN)
                title = f"SEMUA Saham Dekat MA{period} (±3%)"
            else:
                await query.edit_message_text(f"🔍 *Mencari top 50 saham dekat MA{period}...*", parse_mode=ParseMode.MARKDOWN)
                title = f"Top 50 Saham Dekat MA{period} (±3%)"
            
            results = ma_tracker.find_near_ma_stocks(period)
            
        elif callback_data.startswith("ma_cross_"):
            # Cross MA analysis
            period = int(callback_data.split("_")[-1])
            await query.edit_message_text(f"🔍 *Mencari saham cross MA{period}...*", parse_mode=ParseMode.MARKDOWN)
            
            results = ma_tracker.find_cross_ma_stocks(period)
            title = f"Saham Cross MA{period} (Hari ini > MA, Kemarin < MA)"
            show_all = True  # Cross MA selalu tampilkan semua
        
        else:
            return
        
        # Format results (returns list of messages if split)
        messages = ma_tracker.format_results(results, title, show_all)
        
        # Send first message as edit
        await query.edit_message_text(messages[0], parse_mode=ParseMode.MARKDOWN)
        
        # Send additional messages if any
        for additional_message in messages[1:]:
            await query.message.reply_text(additional_message, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ma_callback: {e}")
        await query.edit_message_text(
            "❌ Terjadi kesalahan saat menganalisis data. Silakan coba lagi.",
            parse_mode=ParseMode.MARKDOWN
        )