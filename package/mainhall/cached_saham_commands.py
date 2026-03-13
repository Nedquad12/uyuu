import sys
sys.path.append ("/home/ec2-user/package/cache")
from cached_stock_analyzer import stock_analyzer
from cache_manager import cache_manager
import logging
from imporh import *

logger = logging.getLogger(__name__)

async def format_rupiah(value):
    """Format angka ke Rupiah dengan T/B/M/K"""
    if value >= 1e12:
        return f"{value / 1e12:.2f}T"
    elif value >= 1e9:
        return f"{value / 1e9:.2f}B"
    else:
        return f"{value:,.0f}"

@is_authorized_user 
@spy      
@vip       
async def cache_reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk reload cache data"""
    
    # Send initial message
    processing_msg = await update.message.reply_text("🔄 Reloading cache... Mohon tunggu...")
    
    try:
        start_time = time.time()
        
        # Reload cache
        success, message = await stock_analyzer.reload_cache()
        
        end_time = time.time()
        duration = end_time - start_time
        
        if success:
            final_message = f"✅ **CACHE RELOAD BERHASIL**\n\n"
            final_message += message
            final_message += f"\n\n⏱️ Selesai dalam {duration:.2f} detik"
        else:
            final_message = f"❌ **CACHE RELOAD GAGAL**\n\n"
            final_message += message
        
        await processing_msg.edit_text(final_message, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = f"❌ Error saat reload cache: {str(e)}"
        await processing_msg.edit_text(error_msg)
        logger.error(f"Error in cache_reload_command: {e}")

@is_authorized_user 
@spy      
@vip       
async def cache_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command untuk melihat status cache"""
    
    try:
        cache_info = stock_analyzer.get_cache_status()
        
        if cache_info['status'] == 'Not loaded':
            status_message = "❌ **CACHE STATUS**\n\n"
            status_message += "Status: Not Loaded\n"
            status_message += "Gunakan `/cache_reload` untuk load data"
        else:
            status_message = f"✅ **CACHE STATUS**\n\n"
            status_message += f"📊 Status: {cache_info['status']}\n"
            status_message += f"🕒 Load Time: {cache_info['load_time']}\n"
            status_message += f"💾 Cache Size: {cache_info['cache_size_mb']:.2f} MB\n\n"
            status_message += f"📈 Watchlist Files: {cache_info['watchlist_files']}\n"
            status_message += f"🏢 Sector Files: {cache_info['sector_files']}\n"
            status_message += f"💰 Foreign Data: {'✅' if cache_info['foreign_loaded'] else '❌'}\n\n"
            status_message += "💡 Gunakan `/cache_reload` untuk refresh data"
        
        await update.message.reply_text(status_message, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = f"❌ Error saat mengecek status cache: {str(e)}"
        await update.message.reply_text(error_msg)
        logger.error(f"Error in cache_status_command: {e}")

@is_authorized_user 
@spy      
@vip       
async def saham_cached_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified command handler untuk stock analysis menggunakan cache"""
    
    # Record start time for processing duration
    start_time = time.time()
    
    # Parse command
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ Masukkan kode saham.\nContoh: `/saham BBCA`", 
            parse_mode='Markdown'
        )
        return
    
    stock_code = parts[1].upper()
    
    # Send initial processing message
    processing_msg = await update.message.reply_text(f"🔥 Menganalisis data untuk {stock_code}... Mohon tunggu...")
    
    try:
        # Initialize cache jika belum di-load
        cache_success, cache_msg = await stock_analyzer.initialize_cache()
        if not cache_success:
            await processing_msg.edit_text(f"❌ Error loading cache: {cache_msg}")
            return
        
        # Header message
        header_message = f"📊 **ANALISIS LENGKAP: {stock_code}**\n"
        header_message += f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        header_message += "="*35
        
        await update.message.reply_text(header_message, parse_mode='Markdown')
        
        # 1. VOLUME ANALYSIS
        await update.message.reply_text("📊 Menganalisis Volume dari Cache...")
        volume_analysis, vol_error = stock_analyzer.analyze_stock_volume_cached(stock_code)
        
        if volume_analysis:
            vol_message = f"```\n📈 VOLUME SPIKE ANALYS - {stock_code}\n"
            vol_message += "="*40 + "\n"
            vol_message += f"Harga Saat Ini    : {volume_analysis['current_price']:>12,.0f}\n"
            vol_message += f"Volume Hari Ini   : {volume_analysis['vol_today']:>12,.0f}\n"
            vol_message += f"Rata-rata 7 Hari  : {volume_analysis['avg_7_days']:>12,.0f}\n"
            vol_message += f"Rata-rata 30 Hari : {volume_analysis['avg_30_days']:>12,.0f}\n"
            vol_message += f"Rata-rata 60 Hari : {volume_analysis['avg_60_days']:>12,.0f}\n"
            vol_message += "="*40 + "\n"
            vol_message += f"Spike Hari Ini    : {volume_analysis['spike_today']:>12.2f}x\n"
            vol_message += f"Spike 7 vs 30     : {volume_analysis['spike_7vs30']:>12.2f}x\n"
            vol_message += f"Spike 7 vs 60     : {volume_analysis['spike_7vs60']:>12.2f}x\n"
            vol_message += f"VSA Score         : {volume_analysis['vol_spike']:>12.2f}\n"
            vol_message += "="*40 + "\n"
            vol_message += f"Data Hari         : {volume_analysis['data_points']} hari\n"
            vol_message += f"Status Trending   : {'✅ YA' if volume_analysis['is_trending'] else '❌ TIDAK'}\n"
            vol_message += "```\n"
            
            # Add interpretation
            if volume_analysis['vol_spike'] >= 2.2:
                vol_message += "🚀 **Volume spike tinggi!**"
            elif volume_analysis['is_trending']:
                vol_message += "📈 **Volume dalam tren naik**"
            else:
                vol_message += "😐 **Volume dalam kondisi normal**"
            
            await update.message.reply_text(vol_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Volume: {vol_error}")
        
        # 2. FOREIGN FLOW ANALYSIS
        await update.message.reply_text("🌍 Menganalisis Foreign Flow dari Cache...")
        foreign_analysis, foreign_error = stock_analyzer.analyze_stock_foreign_cached(stock_code)
        
        if foreign_analysis:
            foreign_message = f"```\n🌍 FOREIGN FLOW ANALYSIS - {stock_code}\n"
            foreign_message += "="*45 + "\n"
            foreign_message += f"Foreign Buy Hari Ini  : {foreign_analysis['latest_buy']:>15,.0f}\n"
            foreign_message += f"Foreign Sell Hari Ini : {foreign_analysis['latest_sell']:>15,.0f}\n"
            foreign_message += f"Net Foreign Hari Ini  : {foreign_analysis['latest_net']:>+15,.0f}\n"
            foreign_message += "="*45 + "\n"
            foreign_message += f"Rata-rata Net 7 Hari  : {foreign_analysis['avg_7_days']:>+15,.0f}\n"
            foreign_message += f"Rata-rata Net 30 Hari : {foreign_analysis['avg_30_days']:>+15,.0f}\n"
            foreign_message += f"Rata-rata Net Total   : {foreign_analysis['avg_net']:>+15,.0f}\n"
            foreign_message += "="*45 + "\n"
            
            # Format spike ratio
            if foreign_analysis['spike_ratio'] == float('inf'):
                spike_str = "∞+"
            elif foreign_analysis['spike_ratio'] == float('-inf'):
                spike_str = "∞-"
            else:
                spike_str = f"{foreign_analysis['spike_ratio']:+.2f}x"
            
            foreign_message += f"Spike Ratio           : {spike_str:>15}\n"
            foreign_message += f"Data Points           : {foreign_analysis['data_points']:>15} hari\n"
            foreign_message += f"Tren 7 vs 30 Hari     : {'📈 UP' if foreign_analysis['trend_7vs30'] else '📉 DOWN':>15}\n"
            foreign_message += "```\n"
            
            # Add interpretation
            if foreign_analysis['is_net_positive']:
                if abs(foreign_analysis['spike_ratio']) >= 2.5:
                    foreign_message += "🚀 **Foreign buy spike tinggi! Net buying kuat**"
                else:
                    foreign_message += "💚 **Net foreign buying positif**"
            else:
                foreign_message += "🔴 **Net foreign selling**"
            
            await update.message.reply_text(foreign_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Foreign Flow: {foreign_error}")
        
        # 3. FOREIGN SUMMARY BY PERIODS
        await update.message.reply_text("📊 Menganalisis Foreign Summary dari Cache...")
        foreign_summary = stock_analyzer.get_foreign_summary_cached(stock_code)
        
        if foreign_summary:
            summary_message = f"```\n📊 FOREIGN FLOW SUMMARY - {stock_code}\n"
            summary_message += "="*50 + "\n"
            summary_message += f"{'Period':>6} | {'Buy':>12} | {'Sell':>12} | {'Net':>13}\n"
            summary_message += "="*50 + "\n"
            
            for period, buy, sell, net in foreign_summary:
                summary_message += f"{period:>6} | {buy:>12,.0f} | {sell:>12,.0f} | {net:>+13,.0f}\n"
            
            summary_message += "```"
            await update.message.reply_text(summary_message, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Tidak dapat membuat foreign summary")
        
        # 4. SECTOR ANALYSIS
        await update.message.reply_text("🏢 Menganalisis Data Sektor dari Cache...")
        sector_analysis, sector_error = stock_analyzer.get_stock_sector_cached(stock_code)
        
        if sector_analysis:
            sector_message = f"```\n🏢 SECTOR INFORMATION - {stock_code}\n"
            sector_message += "="*40 + "\n"
            sector_message += f"Sektor            : {sector_analysis['sector']}\n"
            
            # Format tanggal pencatatan if available
            if sector_analysis['tanggal_pencatatan'] is not None:
                if isinstance(sector_analysis['tanggal_pencatatan'], str):
                    sector_message += f"Tanggal Pencatatan: {sector_analysis['tanggal_pencatatan']}\n"
                else:
                    try:
                        # Try to format as date if it's a datetime object
                        import pandas as pd
                        formatted_date = pd.to_datetime(sector_analysis['tanggal_pencatatan']).strftime('%d/%m/%Y')
                        sector_message += f"Tanggal Pencatatan: {formatted_date}\n"
                    except:
                        sector_message += f"Tanggal Pencatatan: {sector_analysis['tanggal_pencatatan']}\n"
            
            # Format papan pencatatan if available
            if sector_analysis['papan_pencatatan'] is not None:
                sector_message += f"Papan Pencatatan  : {sector_analysis['papan_pencatatan']}\n"
            
            sector_message += "```"
            await update.message.reply_text(sector_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ Sektor: {sector_error}")
        
        # 5. MARGIN ANALYSIS (masih menggunakan viewer lama karena tidak di-cache)
        await update.message.reply_text("💰 Menganalisis Margin Trading...")
        try:
            # Import viewer untuk margin analysis (tidak di-cache)
            from utama import TelegramStockDataViewer
            viewer = TelegramStockDataViewer()
            
            viewer.load_margin_files()
            if viewer.margin_df is not None:
                if 'Kode Saham' in viewer.margin_df.columns:
                    stock_margin = viewer.margin_df[viewer.margin_df['Kode Saham'].str.upper() == stock_code.upper()]
                    
                    if not stock_margin.empty:
                        margin_message = f"```\n💰 MARGIN TRADING - {stock_code}\n"
                        margin_message += "="*30 + "\n"
                        margin_message += f"Status: Marginable ✅\n"      
                        margin_message += "```"
                        await update.message.reply_text(margin_message, parse_mode='Markdown')
                    else:
                        await update.message.reply_text(f"ℹ️ Margin: Saham {stock_code} tidak terdaftar dalam margin trading")
                else:
                    await update.message.reply_text("ℹ️ Margin: Format data margin tidak dikenali")
            else:
                await update.message.reply_text("ℹ️ Margin: Data margin tidak tersedia")
                
        except Exception as e:
            logger.error(f"Error in margin analysis: {e}")
            await update.message.reply_text("❌ Error saat menganalisis margin")
        
        # 6. CHART GENERATION (masih menggunakan viewer lama)
        try:
            await update.message.reply_text("📈 Membuat chart margin...")
            from utama import TelegramStockDataViewer
            viewer = TelegramStockDataViewer()
            chart_buffer = viewer.create_margin_charts(stock_code)
            if chart_buffer:
                await update.message.reply_photo(
                    photo=chart_buffer,
                    caption=f"📊 Margin Trading Chart - {stock_code}"
                )
        except Exception as e:
            logger.error(f"Error creating chart: {e}")
        
        # 7. HOLDINGS ANALYSIS (masih menggunakan viewer lama karena kompleks)
        await update.message.reply_text("👥 Menganalisis Holdings Summary...")
        try:
            from utama import TelegramStockDataViewer
            import glob
            import pandas as pd
            
            viewer = TelegramStockDataViewer()
            viewer.load_all_excel_files()
            if viewer.combined_df is not None:
                df = viewer.search_stock(stock_code)
                if df is not None and not df.empty:
                    # Ambil harga penutupan dari cache
                    closing_price = stock_analyzer.get_current_price_cached(stock_code)
                    
                    if closing_price is not None:
                        df['Month'] = df['Date'].dt.to_period('M')
                        holdings_message = f"```\n👥 HOLDINGS SUMMARY - {stock_code}\n"
                        holdings_message += f"💰 Harga Penutupan: Rp {await format_rupiah(closing_price)}\n"
                        holdings_message += "="*45 + "\n"
                        
                        previous_totals = {}
                        for month, group in df.groupby('Month'):
                            totals = {
                                'Ritel': group[['Local ID', 'Foreign ID']].sum().sum() * closing_price,
                                'Bandar Lokal': group[['Local IS', 'Local MF', 'Local SC', 'Local OT']].sum().sum() * closing_price,
                                'Bandar Asing': group[['Foreign IS', 'Foreign MF', 'Foreign SC', 'Foreign OT']].sum().sum() * closing_price,
                                'Big Investor Lokal': group[['Local CP', 'Local PF', 'Local IB', 'Local FD']].sum().sum() * closing_price,
                                'Big Investor Asing': group[['Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign FD']].sum().sum() * closing_price,
                            }
                            
                            holdings_message += f"\n📅 {month.strftime('%b %Y')}\n"
                            for category, total in totals.items():
                                prev_total = previous_totals.get(category, total)
                                change_pct = ((total - prev_total) / prev_total * 100) if prev_total != 0 else 0
                                arrow = "🟩" if change_pct > 0 else "🟥" if change_pct < 0 else "⚪"
                                holdings_message += f"{arrow} {category}: Rp {await format_rupiah(total)} ({change_pct:+.1f}%)\n"
                            
                            holdings_message += "─" * 30 + "\n"
                            previous_totals = totals
                        
                        holdings_message += "```"
                        await update.message.reply_text(holdings_message, parse_mode='Markdown')
                    else:
                        await update.message.reply_text(f"❌ Holdings: Tidak ditemukan harga penutupan untuk {stock_code}")
                else:
                    await update.message.reply_text(f"❌ Holdings: Tidak ada data kepemilikan untuk {stock_code}")
            else:
                await update.message.reply_text("❌ Holdings: Tidak ada data kepemilikan")
        except Exception as e:
            logger.error(f"Error in holdings analysis: {e}")
            await update.message.reply_text(f"❌ Holdings: Error saat menganalisis kepemilikan")
        
        # FINAL SUMMARY WITH CACHE INFO
        summary_msg = f"✅ **RINGKASAN ANALISIS {stock_code}**\n\n"
        
        # Add cache info
        cache_info = stock_analyzer.get_cache_status()
        summary_msg += f"⚡ Cache: {cache_info['cache_size_mb']:.1f}MB | Files: {cache_info['watchlist_files']}\n"
        
        # Add sector info to summary if available
        if sector_analysis:
            summary_msg += f"🏢 Sektor: {sector_analysis['sector']}\n"
        
        if volume_analysis:
            summary_msg += f"📈 VSA Score: {volume_analysis['vol_spike']:.2f} "
            summary_msg += f"({'🚀 HIGH' if volume_analysis['vol_spike'] >= 2.2 else '😐 NORMAL'})\n"
        
        if foreign_analysis:
            summary_msg += f"🌍 Net Foreign: {foreign_analysis['latest_net']:+,.0f} "
            summary_msg += f"({'💚 BUY' if foreign_analysis['is_net_positive'] else '🔴 SELL'})\n"
        
        # Calculate processing time
        end_time = time.time()
        processing_duration = end_time - start_time
        summary_msg += f"\n⏱️ Analisis selesai dalam {processing_duration:.2f} detik"
        summary_msg += f"\n💡 Gunakan `/cache_reload` untuk refresh data"
        
        await update.message.reply_text(summary_msg, parse_mode='Markdown')
        
        # Delete processing message
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in saham_cached_command: {e}")
        await processing_msg.edit_text(f"❌ Terjadi error: {str(e)}")
    
    finally:
        # Clean up memory
        import matplotlib.pyplot as plt
        import gc
        plt.close('all')
        gc.collect()

# Command handlers mapping
CACHE_COMMANDS = {
    'cache_reload': cache_reload_command,
    'cache_status': cache_status_command,
    'saham': saham_cached_command  # Replace original saham command
}