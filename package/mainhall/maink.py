from vol import crypto_vol_command
from main_dtm import cmd_crypto_analyze
from ma import ma_command, get_ma_callback_handler, start_ma_cache_reload, stop_ma_cache_reload
from mf import mf_command
from ff import ff_command 
from mff import mff_command
from rasio import rasio_command
from rate_limiter import cmd_quota_status
from vsa import crypto_vsa_command
from price import price_command, price_all_command
from vwap import vwap_command
from cm import cm_command, cm_callback_handler
from vva import vva_command
from wh import wh_command, wh_callback_handler
from news import (
    news_command, 
    get_news_callback_handler, 
    news_channel_command,
    start_auto_monitoring,
    cleanup_monitoring,
    news_bot
)  
from crypto_tight_commands import setup_crypto_jobs, cvt_command, ct_command, creload_command, cstatus_command
from liq import liq_command, liq_callback_handler 
import sys
from sistem import run_command, kill_command, ram_command, cpu_command, list_command
sys.path.append ("/home/ec2-user/kripto/admin")
from admin_command import get_admin_conversation_handler
from auth import load_roles
import pytz
from imporh import *
import signal
import atexit

load_roles()
BOT_TOKEN="8389458809:AAEiPRHNsRxW8T610vSRxd7dckB8FmJc0Hk"

@vip   
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help - menampilkan daftar semua command yang tersedia"""
    help_text = """ 
📚 **Panduan Singkat & Gampang – Bot Crypto**
🔑 Cara Pakai Umum

**Available Commands:**
• `/help` - Tampilkan panduan ini
• `/p <ticker>` - Analisis harga crypto dengan chart 200 hari
• `/pa <ticker>` - Analisis harga crypto dengan chart daily, weekly dan mothly
• `/cm <ticker>` - Melihat flow
• `/liq <ticker>` - Melihat liquidation chart  
• `/ff`- Menampilkan funding fee diatas 0.5%
• `/vol` - Analisis volume spike crypto
• `/c` - Analisis chart daily, weekly dan monthly
• `/ma` - Analisis Moving Average (MA 20/60/100/200/400) ⚡ **CACHED**
• `/rasio` - Analisis rasio Long/Short Future
• `/vol` - Melihat daftar kripto yang memiliki vsa tinggi
• `/vsa` - Melihat Volume
• `/vva` - Melihat Volume 24h
• `/wh` - Melihat perbandng big vs small
• `/quota` - Cek batas pemakaian untuk free user

📚 **News Commands (NEW!):**
• `/news` - Menu realtime crypto news (Interactive)
• `/newsch` - Kirim berita crypto ke channel
• `/news_start` - Start realtime monitoring
• `/news_stop` - Stop realtime monitoring  
• `/news_status` - Check monitoring status

💡 **Tips:** Semua analisis menggunakan data real-time dari Binance
⚡ **Update:** MA analysis menggunakan cache untuk loading super cepat!
🔄 **Auto-Reload:** Cache MA diperbarui otomatis setiap 35 menit
🚨 **NEW:** Realtime crypto news monitoring setiap 10 menit!
    """ 
    await update.message.reply_text(help_text, parse_mode='Markdown')
    
@vip   
async def news_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk start realtime news monitoring"""
    if news_bot.is_monitoring:
        await update.message.reply_text("🚨 Realtime news monitoring sudah berjalan!")
        return
        
    try:
        await update.message.reply_text("🚀 Memulai realtime news monitoring...")
        
        # Start monitoring task
        import asyncio
        news_bot.monitor_task = asyncio.create_task(
            news_bot.start_monitoring(context.application)
        )
        
        await update.message.reply_text(
            "✅ Realtime news monitoring berhasil dimulai!\n\n"
            "📡 **Status:** Monitoring aktif\n"
            "🕐 **Interval:** Setiap 10 menit\n" 
            "📰 **Sources:** CoinTelegraph, CoinDesk, Bloomberg Tech, Bisnis.com\n"
            "📢 **Output:** Otomatis ke channel untuk berita crypto baru\n\n"
            "Gunakan /news_stop untuk menghentikan monitoring."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error memulai monitoring: {e}")

@vip   
async def news_stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk stop realtime news monitoring"""
    if not news_bot.is_monitoring:
        await update.message.reply_text("ℹ️ Realtime news monitoring sudah berhenti!")
        return
        
    try:
        news_bot.stop_monitoring()
        await update.message.reply_text(
            "ℹ️ Realtime news monitoring dihentikan!\n\n"
            "📊 **Status:** Monitoring nonaktif\n"
            "💾 **Data:** Tersimpan untuk restart berikutnya\n\n"
            "Gunakan /news_start untuk memulai lagi."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error menghentikan monitoring: {e}")

@vip   
async def news_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk check status news monitoring"""
    try:
        status = "🟢 AKTIF" if news_bot.is_monitoring else "🔴 NONAKTIF"
        total_sent = len(news_bot.sent_articles)
        
        # Format last check times
        last_check_info = ""
        if news_bot.last_check:
            for source, last_time in news_bot.last_check.items():
                try:
                    from datetime import datetime
                    check_time = datetime.fromisoformat(last_time)
                    formatted_time = check_time.strftime('%d/%m/%Y %H:%M WIB')
                    display_name = source.replace('_', ' ')
                    last_check_info += f"  • {display_name}: {formatted_time}\n"
                except:
                    display_name = source.replace('_', ' ')
                    last_check_info += f"  • {display_name}: Belum pernah dicek\n"
        else:
            last_check_info = "  • Belum ada pengecekan\n"
        
        status_message = f"""
📊 **Status Realtime News Monitoring**

🔄 **Status Monitor:** {status}
📈 **Total artikel terkirim:** {total_sent}
📡 **RSS Sources:** 4 feeds aktif

📰 **Sources yang dimonitor:**
  • CoinTelegraph - Crypto news
  • CoinDesk - Blockchain analysis  
  • Bloomberg Tech - Technology (crypto filter)
  • Bisnis.com - Indonesia economy (crypto filter)

⏰ **Pengecekan terakhir:**
{last_check_info}
🕐 **Interval check:** 10 menit
📡 **Target channel:** {news_bot.application.bot if news_bot.application else 'Not set'}
🔍 **Filter:** Hanya artikel crypto/blockchain

**Control Commands:**
/news_start - Mulai monitoring
/news_stop - Stop monitoring
/news - Interactive menu
        """
        
        await update.message.reply_text(status_message, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting status: {e}")

# Graceful shutdown handler
def signal_handler(sig, frame):
    """Handle graceful shutdown"""
    print("\n🔄 Shutting down bot gracefully...")
    import asyncio
    asyncio.create_task(cleanup_monitoring())
    asyncio.create_task(stop_ma_cache_reload())
    sys.exit(0)

# Setup untuk post-init dan post-shutdown
async def post_init_callback(application):
    """Callback yang dipanggil setelah bot berhasil start"""
    print("✅ Bot berhasil dimulai!")
    
    # Auto-start MA cache reload
    try:
        print("🚀 Starting MA cache auto-reload system...")
        start_ma_cache_reload(application)
        print("✅ MA cache auto-reload started! (30s delay, then every 35 min)")
    except Exception as e:
        print(f"❌ Error starting MA cache reload: {e}")
    
    # Auto-start realtime news monitoring
    try:
        print("🚀 Starting auto realtime news monitoring...")
        await start_auto_monitoring(application)
        print("✅ Realtime news monitoring started successfully!")
    except Exception as e:
        print(f"❌ Error starting auto monitoring: {e}")

async def post_shutdown_callback(application):
    """Callback yang dipanggil saat bot shutdown"""
    print("🔄 Bot sedang shutdown...")
    
    # Stop MA cache reload
    try:
        await stop_ma_cache_reload()
        print("✅ MA cache auto-reload stopped")
    except Exception as e:
        print(f"❌ Error stopping MA cache reload: {e}")
    
    # Stop news monitoring
    await cleanup_monitoring()
    print("✅ Bot shutdown completed!")
  
def main(): 
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(lambda: asyncio.run(cleanup_monitoring()))
    atexit.register(lambda: asyncio.run(stop_ma_cache_reload()))
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", help_command)) 
    app.add_handler(CommandHandler("p", price_command)) 
    app.add_handler(CommandHandler("pa", price_all_command))
    app.add_handler(CommandHandler("vol", crypto_vol_command)) 
    app.add_handler(CommandHandler("vva", vva_command)) 
    app.add_handler(CommandHandler("c", cmd_crypto_analyze)) 
    app.add_handler(CommandHandler("ma", ma_command)) 
    app.add_handler(CommandHandler("mf", mf_command)) 
    app.add_handler(CommandHandler("ff", ff_command)) 
    app.add_handler(CommandHandler("mff", mff_command)) 
    app.add_handler(CommandHandler("rasio", rasio_command)) 
    app.add_handler(CommandHandler("quota", cmd_quota_status)) 
    app.add_handler(CommandHandler("vsa", crypto_vsa_command)) 
    app.add_handler(CommandHandler("vwap", vwap_command)) 
    app.add_handler(CommandHandler("liq", liq_command)) 
    app.add_handler(CommandHandler("cm", cm_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("kill", kill_command))
    app.add_handler(CommandHandler("ram", ram_command))
    app.add_handler(CommandHandler("cpu", cpu_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("newsch", news_channel_command))
    app.add_handler(CommandHandler("news_start", news_start_command))
    app.add_handler(CommandHandler("news_stop", news_stop_command))
    app.add_handler(CommandHandler("news_status", news_status_command))
    app.add_handler(CommandHandler("wh", wh_command))
    app.add_handler(CommandHandler("cvt", cvt_command))
    app.add_handler(CommandHandler("ct", ct_command))
    app.add_handler(CommandHandler("creload", creload_command))
    app.add_handler(CommandHandler("cstatus", cstatus_command))
    app.add_handler(CallbackQueryHandler(cm_callback_handler, pattern=r'^cm_'))
    app.add_handler(CallbackQueryHandler(liq_callback_handler, pattern=r'^liq_'))
    app.add_handler(CallbackQueryHandler(wh_callback_handler, pattern=r'^wh_'))
    app.add_handler(get_ma_callback_handler()) 
    app.add_handler(get_news_callback_handler())
    app.add_handler(get_admin_conversation_handler()) 
    app.post_init = post_init_callback
    app.post_shutdown = post_shutdown_callback
    
    setup_crypto_jobs(app)
    
    print("🚀 Starting Crypto Bot with Advanced Features...")
    print("📡 Auto-monitoring: CoinTelegraph, CoinDesk, Bloomberg Tech, Bisnis.com")
    print("⏰ News check interval: 10 minutes")
    print("📢 Auto-send crypto news to channel")
    print("⚡ MA Cache system: Auto-reload every 35 minutes")
    print("🔄 Initial MA cache load: 30 seconds after start")
    print("💾 Cached MA periods: 20, 60, 100, 200, 400")
    print("✅ Bot siap digunakan!")
    
    # Run the bot
    try:
        app.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        print("\n🔄 Bot dihentikan oleh user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")
    finally:
        print("🧹 Cleaning up...")
        import asyncio
        asyncio.run(cleanup_monitoring())
        asyncio.run(stop_ma_cache_reload())
        print("✅ Cleanup completed!") 
    
if __name__ == "__main__": 
  main()