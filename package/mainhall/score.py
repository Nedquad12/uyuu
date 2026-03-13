from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import logging
import sys
sys.path.append ("/home/ec2-user/package/machine")
from score_machine import ip_tracker
from imporh import is_authorized_user, spy, vip

logger = logging.getLogger(__name__)


@is_authorized_user 
@spy      
@vip       
async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ip [KODE]"""
    
    try:
        # Check if data sudah di-load
        if not ip_tracker.ram_cache or not ip_tracker.ip_cache:
            await update.message.reply_text(
                "⚠️ Data belum tersedia, hubungi admin"
            )
            return
        
        # Check jika ada argument (kode saham)
        if context.args and len(context.args) > 0:
            stock_code = context.args[0].upper()
            
            await update.message.reply_text(f"⏳ Memuat data IP untuk {stock_code}...")
            
            # Get specific stock
            stock_data = ip_tracker.get_stock(stock_code)
            
            if stock_data:
                message = ip_tracker.format_single_stock(stock_data)
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(f"❌ Data untuk {stock_code} tidak ditemukan.")
        else:
            # Show all stocks
            await update.message.reply_text("⏳ Memuat semua data Indikator Poin...")
            
            # Get all stocks sorted by IA
            results = ip_tracker.get_all_stocks()
            
            # Format and send results
            messages = ip_tracker.format_results(results)
            
            for msg in messages:
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ip_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


@is_authorized_user
async def reload_ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /reload_ip"""
    await update.message.reply_text("🔄 Memuat ulang data Indikator Poin...")
    
    try:
        ip_tracker.reload_data()
        
        cache_info = ip_tracker.get_cache_info()
        info_text = f"✅ *Data berhasil di-reload!*\n\n"
        info_text += f"📊 Files loaded: {cache_info['files_loaded']}\n"
        info_text += f"📈 Stocks calculated: {cache_info['stocks_with_ip']}\n"
        info_text += f"💾 RAM usage: {cache_info['total_memory_mb']:.1f} MB\n"
        
        if cache_info['last_reload']:
            info_text += f"🕒 Last reload: {cache_info['last_reload'].strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in reload_ip_command: {e}")
        await update.message.reply_text(f"❌ Error reload: {str(e)}")


@is_authorized_user 
@spy      
@vip
async def ip_top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ip_top [N] - Tampilkan top N saham"""
    
    try:
        # Check if data sudah di-load
        if not ip_tracker.ram_cache or not ip_tracker.ip_cache:
            await update.message.reply_text(
                "⚠️ Data belum tersedia, hubungi admin"
            )
            return
        
        # Get top N parameter (default 20)
        top_n = 20
        if context.args and len(context.args) > 0:
            try:
                top_n = int(context.args[0])
                if top_n < 1:
                    top_n = 20
                elif top_n > 100:
                    top_n = 100
            except ValueError:
                top_n = 20
        
        await update.message.reply_text(f"⏳ Memuat top {top_n} saham dengan IA tertinggi...")
        
        # Get all stocks sorted by IA
        all_results = ip_tracker.get_all_stocks()
        
        # Take only top N
        results = all_results[:top_n]
        
        # Format and send results
        messages = ip_tracker.format_results(results)
        
        for msg in messages:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ip_top_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


@is_authorized_user 
@spy      
@vip
async def ip_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ip_filter [min_ia] - Filter saham berdasarkan IA minimum"""
    
    try:
        # Check if data sudah di-load
        if not ip_tracker.ram_cache or not ip_tracker.ip_cache:
            await update.message.reply_text(
                "⚠️ Data belum tersedia, hubungi admin"
            )
            return
        
        # Get min_ia parameter (default 3.0)
        min_ia = 3.0
        if context.args and len(context.args) > 0:
            try:
                min_ia = float(context.args[0])
            except ValueError:
                min_ia = 3.0
        
        await update.message.reply_text(f"⏳ Memuat saham dengan IA ≥ {min_ia}...")
        
        # Get all stocks and filter
        all_results = ip_tracker.get_all_stocks()
        results = [stock for stock in all_results if stock['ia'] >= min_ia]
        
        if not results:
            await update.message.reply_text(f"❌ Tidak ada saham dengan IA ≥ {min_ia}")
            return
        
        # Format and send results
        messages = ip_tracker.format_results(results)
        
        for msg in messages:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ip_filter_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


@is_authorized_user 
@spy      
@vip
async def ip_bullish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ip_bullish - Filter saham bullish di semua timeframe"""
    
    try:
        # Check if data sudah di-load
        if not ip_tracker.ram_cache or not ip_tracker.ip_cache:
            await update.message.reply_text(
                "⚠️ Data belum tersedia, hubungi admin"
            )
            return
        
        await update.message.reply_text("⏳ Memuat saham bullish di semua timeframe...")
        
        # Get all stocks and filter bullish (IPd, IPw, IPm > 0)
        all_results = ip_tracker.get_all_stocks()
        results = [
            stock for stock in all_results 
            if stock['ipd'] > 0 and stock['ipw'] > 0 and stock['ipm'] > 0
        ]
        
        if not results:
            await update.message.reply_text("❌ Tidak ada saham yang bullish di semua timeframe")
            return
        
        # Format and send results
        messages = ip_tracker.format_results(results)
        
        for msg in messages:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ip_bullish_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


@is_authorized_user 
@spy      
@vip
async def ip_bearish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ip_bearish - Filter saham bearish di semua timeframe"""
    
    try:
        # Check if data sudah di-load
        if not ip_tracker.ram_cache or not ip_tracker.ip_cache:
            await update.message.reply_text(
                "⚠️ Data belum tersedia, hubungi admin"
            )
            return
        
        await update.message.reply_text("⏳ Memuat saham bearish di semua timeframe...")
        
        # Get all stocks and filter bearish (IPd, IPw, IPm < 0)
        all_results = ip_tracker.get_all_stocks()
        results = [
            stock for stock in all_results 
            if stock['ipd'] < 0 and stock['ipw'] < 0 and stock['ipm'] < 0
        ]
        
        if not results:
            await update.message.reply_text("❌ Tidak ada saham yang bearish di semua timeframe")
            return
        
        # Format and send results
        messages = ip_tracker.format_results(results)
        
        for msg in messages:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ip_bearish_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def ip_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ip_info - Info tentang cache IP"""
    
    try:
        cache_info = ip_tracker.get_cache_info()
        
        info_text = "*Indikator Poin - Cache Info*\n\n"
        info_text += f"📁 Files loaded: {cache_info['files_loaded']}/{cache_info['total_files_available']}\n"
        info_text += f"📊 Stocks calculated: {cache_info['stocks_with_ip']}\n"
        info_text += f"💾 RAM usage: {cache_info['ram_usage_mb']:.1f} MB\n"
        info_text += f"💾 IP cache: {cache_info['ip_cache_mb']:.2f} MB\n"
        info_text += f"💾 Total memory: {cache_info['total_memory_mb']:.1f} MB\n"
        
        if cache_info['last_reload']:
            info_text += f"\n🕒 Last reload: {cache_info['last_reload'].strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            info_text += f"\n⚠️ Data belum pernah di-load"
        
        await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ip_info_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")