from main_dtm import cmd_calculate1, cmd_calculate_us, cmd_screener, screener_callback
from stockdata import show_indices_data, free_float_summary, valuation_dual
from holdinghand import handle_chart_selection, create_chart, watchlist_command, search_stock_command, holdings_summary_with_stock, handle_watchlist_filter, handle_watchlist_pagination, reload7_cache_command
from orderh import broker_detail, load_combined_stock, load_stock, broker_analysis, pie_chart, button_callback, handle_file_upload_order
from reload import reload_cache
from blackrock import blackrock_indonesia, blackrock_significant_movements, blackrock_dim, blackrock_x, blackrock_jp, blackrock_spdr, blackrock_fid, blackrock_gs, blackrock_inv, blackrock_sch, blackrock_ws,blackrock_all, blackrock_col, blackrock_ksa
from databulanan import margin_trading, export_stock, asing_flow
from domh import domisili_analysis, domisili_detail, load_dom, button_callbackdom, pie_chart_dom, handle_file_upload_dom
from user_info import get_id_pengguna
from fspike import fspike_command
from vol import vol_command, reload_cache_command
from rate_limiter import cmd_quota_status
from saham_unified import saham_command
from super_analysis import super_command
from sektor import sektor_command, sektor_detail_command
from help_video import helpvideo_command, helpvideo_callback
from cache import preload_cache
from flowh import load_flow_data, flow_analysis, flow_button_callback, handle_file_upload_flow
from ma_full import (
    ma_command,
    cma_command, 
    am_command,
    low_command,
    reload_command,
    cache_info_command,
    ma_callback
)

from stock_scoring import stock_score_command
from score import (
        ip_command, 
        reload_ip_command, 
        ip_top_command, 
        ip_filter_command,
        ip_bullish_command,
        ip_bearish_command,
        ip_info_command
    )
from boom import boom_command, boom_tracker, reload3_command
from tight_full import vt_command, t_command
from ms_full import ms_command, reload4_command, ms_callback, ms_tracker
from freq import freq_command, reload6_cache_command
from stock_summary import stock3_command
from cc import cc_command, reload10_command
from cons import cons_command, cons_callback
import sys
sys.path.append ("/home/ec2-user/package/admin")
from admin_command import get_admin_conversation_handler
from auth import load_roles
from repo import repo_command
from imporh import *
from fall import reload9_cache_command, fall_command, fall_callback, fall_back_callback
from stock_holdings import cmd_sh, callback_mode, handle_search_input
from telegram.request import HTTPXRequest

load_roles()
preload_cache

BOT_TOKEN="8212869606:AAGvs-HoLJfSCQ27zHofgH8wAsp7BJnYxz0"

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help - menampilkan daftar semua command yang tersedia"""
    
    help_text = """
📘 *Panduan Singkat & Gampang – Bot Saham*

🔑 *Cara Pakai Umum*
• Semua perintah diawali dengan /
• Beberapa perintah wajib diikuti ticker/kode saham
• Format umum: `/perintah TICKER`

*Contoh:*
• `/c BBCA` → lihat tren BBCA
• `/bi BBCA` → lihat kepemilikan Blackrock untuk BBCA

📊 *Perintah Utama (WAJIB pakai ticker)*
• `/3` → ringkasan lengkap 1 saham (FSA, VSA, MACD, Stochastic, Foreign Spike, MA status)
  Format: `/3 KODE_SAHAM`
  Contoh: `/3 BBCA`
• `/ss` → stock scoring (skor saham berdasarkan indikator)
  Format: `/ss KODE_SAHAM`
  Contoh: `/ss BBCA`
• `/c` → trend saham Indonesia
• `/ff` → free float / market cap beredar
• `/saham` → profil saham (VSA, FSA, shareholder, profil perusahaan)
• `/hol` → detail shareholder
• `/asing` → data transaksi asing (10–60 hari)
• `/m` → data transaksi margin

📈 *WATCHLIST Saham:*
• `/wl` → daftar watchlist (saham dengan lonjakan volume ≥70% dari VMA60)
• `/fspike` → Menampilkan pembelian saham oleh asing
• `/vsa` → Analisis spike volume
• `/boom` → saham volume gede tapi belum naik banyak
  Cocok buat: saham yang lagi dikumpulin, potensi naik
• `/ms` → lihat sinyal beli/jual teknikal
  Tampilkan saham dengan sinyal MACD atau Stochastic
• `/fsa` → lihat spike frekuensi

🔍 *Data saham*
• `/search` → kepemilikan lokal vs asing
• `/cons` → mengetahui transaksi institusi perbulan
• `/ex` → melihat data pergerakan institusi secara lengkap

💰 *Kepemilikan Blackrock:*
• `/bi` - BlackRock

📊 *MA TRACKER (Moving Average Analysis):*
• `/ma` → saham dekat MA (dalam range ±3% dari MA)
• `/cma` → saham cross MA (nembus MA hari ini vs kemarin)
• `/am` → saham above all MA (di atas MA20,60,120,200)
• `/lm` → saham dibawah all MA (di bawah MA20,60,120,200)

🎯 *CARI SAHAM SIAP NAIK:*
• `/vt` → saham nempel banget ke MA, belum naik jauh (<5%)
  Cocok buat: beli awal, nunggu breakout
• `/t` → saham udah mulai jauh dari MA (5-7%)
  Cocok buat: saham yang udah mulai ada momentum
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_file_upload_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route file upload based on caption"""
    user_id = update.effective_user.id
    message = update.message
    
    # Hanya proses jika ada dokumen
    if not message.document:
        await message.reply_text("❌ Harap kirim file Excel (.xlsx) atau .txt")
        return
    
    # Cek caption
    caption = message.caption
    
    if caption:
        if caption.startswith("/dom"):
            # Route ke DOM handler
            await handle_file_upload_dom(update, context)
            return
        elif caption.startswith("/stock"):
            # Route ke Order handler  
            await handle_file_upload_order(update, context)
            return
        elif caption.startswith("/flow"):
            # Route ke Flow handler
            await handle_file_upload_flow(update, context)
            return
    
    # Jika tidak ada caption atau caption tidak dikenali
    await message.reply_text(
        "⚠️ Sertakan caption /dom, /stock, atau /flow saat upload file\n\n"
        "Contoh:\n"
        "🔎 Upload file dengan caption: /dom\n"
        "🔎 Upload file dengan caption: /stock\n"
        "🔎 Upload file dengan caption: /flow"
    )
 
def main():
    # Konfigurasi timeout 45 detik
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=45.0,
        write_timeout=45.0,
        connect_timeout=45.0,
        pool_timeout=45.0
    )
    
    # Build application dengan request yang sudah dikonfigurasi
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("helpvideo", helpvideo_command))
    app.add_handler(CommandHandler("saham", saham_command))
    app.add_handler(CommandHandler("id", get_id_pengguna))
    app.add_handler(CommandHandler("quota", cmd_quota_status))
    app.add_handler(CommandHandler("cc", cmd_calculate1))
    app.add_handler(CommandHandler("us", cmd_calculate_us))
    app.add_handler(CommandHandler("reload", reload_cache))
    app.add_handler(CommandHandler("m", margin_trading))
    app.add_handler(CommandHandler("ex", export_stock))
    app.add_handler(CommandHandler("bi", blackrock_indonesia))
    app.add_handler(CommandHandler("b7", blackrock_significant_movements))
    app.add_handler(CommandHandler("search", search_stock_command))
    app.add_handler(CommandHandler("dim", blackrock_dim))
    app.add_handler(CommandHandler("spdr", blackrock_spdr))
    app.add_handler(CommandHandler("sch", blackrock_sch))
    app.add_handler(CommandHandler("fid", blackrock_fid))
    app.add_handler(CommandHandler("inv", blackrock_inv))
    app.add_handler(CommandHandler("ws", blackrock_ws))
    app.add_handler(CommandHandler("gs", blackrock_gs))
    app.add_handler(CommandHandler("jp", blackrock_jp))
    app.add_handler(CommandHandler("x", blackrock_x))
    app.add_handler(CommandHandler("col", blackrock_col))
    app.add_handler(CommandHandler("all", blackrock_indonesia))
    app.add_handler(CommandHandler("wl", watchlist_command))
    app.add_handler(CommandHandler("i", show_indices_data))
    app.add_handler(CommandHandler("chart", create_chart))
    app.add_handler(CommandHandler("ff", free_float_summary))
    app.add_handler(CommandHandler("hol", holdings_summary_with_stock))
    app.add_handler(CommandHandler("screen133", cmd_screener))
    app.add_handler(CommandHandler("asing", asing_flow))
    app.add_handler(CommandHandler("stock", load_stock))
    app.add_handler(CommandHandler("dom", load_dom))
    app.add_handler(CommandHandler("sa", load_combined_stock))
    app.add_handler(CommandHandler("detail", broker_detail))
    app.add_handler(CommandHandler("detaildom", domisili_detail))
    app.add_handler(CommandHandler("broker", broker_analysis)) 
    app.add_handler(CommandHandler("domisili", domisili_analysis))
    app.add_handler(CommandHandler("pie", pie_chart))
    app.add_handler(CommandHandler("piedom", pie_chart_dom))
    app.add_handler(CommandHandler("val", valuation_dual))
    app.add_handler(CommandHandler("repo", repo_command))
    app.add_handler(CommandHandler("fspike", fspike_command))
    app.add_handler(CommandHandler("vsa", vol_command))
    app.add_handler(CommandHandler("super", super_command))
    app.add_handler(CommandHandler("flow", load_flow_data))
    app.add_handler(CommandHandler("flowanalysis", flow_analysis))
    app.add_handler(CommandHandler("sektor", sektor_command))
    app.add_handler(CommandHandler("detailsektor", sektor_detail_command))
    app.add_handler(CommandHandler("ma", ma_command))
    app.add_handler(CommandHandler("cma", cma_command))
    app.add_handler(CommandHandler("am", am_command))
    app.add_handler(CommandHandler("lm", low_command))
    app.add_handler(CommandHandler("reload2", reload_command))
    app.add_handler(CommandHandler("cacheinfo", cache_info_command))
    app.add_handler(CommandHandler("vt", vt_command))
    app.add_handler(CommandHandler("t", t_command))
    app.add_handler(CommandHandler("boom", boom_command))
    app.add_handler(CommandHandler("reload3", reload3_command))
    app.add_handler(CommandHandler("ms", ms_command))
    app.add_handler(CommandHandler("reload4", reload4_command))
    app.add_handler(CommandHandler("reload5", reload_cache_command))
    app.add_handler(CommandHandler("fsa", freq_command))
    app.add_handler(CommandHandler("reload6", reload6_cache_command))
    app.add_handler(CommandHandler("3", stock3_command))
    app.add_handler(CommandHandler("reload7", reload7_cache_command))
    app.add_handler(CommandHandler("ip", ip_command))
    app.add_handler(CommandHandler("reload8", reload_ip_command))
    app.add_handler(CommandHandler("ip_top", ip_top_command))
    app.add_handler(CommandHandler("ip_filter", ip_filter_command))
    app.add_handler(CommandHandler("ip_bullish", ip_bullish_command))
    app.add_handler(CommandHandler("ip_bearish", ip_bearish_command))
    app.add_handler(CommandHandler("ip_info", ip_info_command))
    app.add_handler(CommandHandler("ss", stock_score_command))   
    app.add_handler(CommandHandler("reload9", reload9_cache_command))
    app.add_handler(CommandHandler("fall", fall_command))
    app.add_handler(CommandHandler("cons", cons_command))
    app.add_handler(CommandHandler("c", cc_command))
    app.add_handler(CommandHandler("reload10", reload10_command))
    app.add_handler(CommandHandler("sh", cmd_sh))
    app.add_handler(get_admin_conversation_handler())
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload_router))
    app.add_handler(CallbackQueryHandler(helpvideo_callback, pattern="^video_"))
    app.add_handler(CallbackQueryHandler(ma_callback, pattern="^ma_"))
    app.add_handler(CallbackQueryHandler(ms_callback, pattern="^ms_"))
    app.add_handler(CallbackQueryHandler(cons_callback, pattern="^cons_"))
    app.add_handler(CallbackQueryHandler(screener_callback, pattern="^(next_screener|prev_screener)$"))
    app.add_handler(CallbackQueryHandler(flow_button_callback, pattern="^flow_"))
    app.add_handler(CallbackQueryHandler(handle_watchlist_pagination, pattern=r'^wl_page_'))
    app.add_handler(CallbackQueryHandler(handle_watchlist_filter, pattern=r'^wl_'))
    app.add_handler(CallbackQueryHandler(handle_chart_selection, pattern=r'^(field_generate_chart_).*|^select_all$|^clear_all$'))
    app.add_handler(CallbackQueryHandler(button_callbackdom, pattern="^(dom_broker_|dom_pie_|dom_detail_)"))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(broker_|pie_|detail_)"))
    app.add_handler(CallbackQueryHandler(fall_callback, pattern="^fall_(1d|1w|1m|1q)$"))
    app.add_handler(CallbackQueryHandler(fall_back_callback, pattern="^fall_back$"))
    app.add_handler(CallbackQueryHandler(callback_mode, pattern="^mode_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_input))
        
    loop = asyncio.get_event_loop()
    print("✅ Bot jalan...")
    app.run_polling()
    
if __name__ == "__main__":
   main()
