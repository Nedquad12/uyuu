from imporh import *
import sys
import time
from cache import read_or_cache
from excel_reader import get_file_date_from_name, get_excel_files, get_stock_sector_data
sys.path.append("/home/ec2-user/package/machine")
from utama import TelegramStockDataViewer

async def format_rupiah(value):
    """Format angka ke Rupiah dengan T/B/M/K"""
    if value >= 1e12:
        return f"{value / 1e12:.2f}T"
    elif value >= 1e9:
        return f"{value / 1e9:.2f}B"
    else:
        return f"{value:,.0f}"

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize viewer
viewer = TelegramStockDataViewer()

def analyze_stock_volume(stock_code):
    """Analyze volume for specific stock"""
    try:
        directory = "/home/ec2-user/database/wl"
        excel_files = get_excel_files(directory)
        
        if len(excel_files) < 7:
            return None, "Tidak cukup data untuk analisis (minimal 7 file)"
        
        excel_files = excel_files[:60]
        volume_data = []
        
        for file_info in excel_files:
            df = read_or_cache(file_info['path'])
            if df is None:
                continue
            
            # Find stock data
            stock_row = df[df['kode_saham'] == stock_code]
            if not stock_row.empty:
                volume_data.append({
                    'date': file_info['date'],
                    'volume': stock_row.iloc[0]['volume'],
                    'price': stock_row.iloc[0]['penutupan']
                })
        
        if len(volume_data) < 7:
            return None, f"Tidak cukup data untuk {stock_code} (ditemukan {len(volume_data)} hari)"
        
        # Sort by date (newest first)
        volume_data.sort(key=lambda x: x['date'], reverse=True)
        
        # Calculate volume analysis
        volumes = [item['volume'] for item in volume_data]
        vol_today = volumes[0]
        avg_7_days = sum(volumes[:7]) / 7
        avg_30_days = sum(volumes[:30]) /30
        max_days = min(len(volumes), 60)
        avg_60_days = sum(volumes[:max_days]) / max_days
        
        # Calculate spikes
        spike_today = vol_today / avg_7_days if avg_7_days > 0 else 0
        spike_7vs30 = avg_7_days / avg_30_days if avg_30_days > 0 else 0
        spike_7vs60 = avg_7_days / avg_60_days if avg_60_days > 0 else 0
        vol_spike = (spike_today + spike_7vs60 + spike_7vs30) / 3
        
        analysis = {
            'stock_code': stock_code,
            'vol_today': vol_today,
            'avg_7_days': avg_7_days,
            'avg_30_days': avg_30_days,
            'avg_60_days': avg_60_days,
            'spike_today': spike_today,
            'spike_7vs60': spike_7vs60,
            'vol_spike': vol_spike,
            'current_price': volume_data[0]['price'],
            'data_points': len(volume_data),
            'is_trending': avg_7_days > avg_60_days and vol_today > avg_7_days
        }
        
        return analysis, None
        
    except Exception as e:
        logger.error(f"Error in analyze_stock_volume: {e}")
        return None, "Error saat menganalisis volume"

def analyze_stock_foreign(stock_code):
    """Analyze foreign flow for specific stock"""
    try:
        directory = "/home/ec2-user/database/wl"
        excel_files = get_excel_files(directory)
        
        if len(excel_files) < 2:
            return None, "Tidak cukup data untuk analisis foreign"
        
        excel_files = excel_files[:60]
        foreign_data = []
        
        for file_info in excel_files:
            df = read_or_cache(file_info['path'])
            if df is None:
                continue
            
            # Find stock data
            stock_row = df[df['kode_saham'] == stock_code]
            if not stock_row.empty:
                row_data = stock_row.iloc[0]
                foreign_data.append({
                    'date': file_info['date'],
                    'foreign_buy': row_data['foreign_buy'],
                    'foreign_sell': row_data['foreign_sell'],
                    'foreign_net': row_data['foreign_net'],
                    'price': row_data['penutupan']
                })
        
        if len(foreign_data) < 2:
            return None, f"Tidak cukup data foreign untuk {stock_code}"
        
        # Sort by date (newest first)
        foreign_data.sort(key=lambda x: x['date'], reverse=True)
        
        # Calculate foreign analysis
        net_flows = [item['foreign_net'] for item in foreign_data]
        latest_net = net_flows[0]
        avg_net = sum(net_flows) / len(net_flows)
        
        # Calculate spike
        if avg_net != 0:
            spike_ratio = latest_net / avg_net
        else:
            if latest_net > 0:
                spike_ratio = float('inf')
            elif latest_net < 0:
                spike_ratio = float('-inf')
            else:
                spike_ratio = 0
        
        # Calculate 7-day and 30-day averages
        avg_7_days = sum(net_flows[:min(7, len(net_flows))]) / min(7, len(net_flows))
        avg_30_days = sum(net_flows[:min(30, len(net_flows))]) / min(30, len(net_flows))
        
        analysis = {
            'stock_code': stock_code,
            'latest_net': latest_net,
            'latest_buy': foreign_data[0]['foreign_buy'],
            'latest_sell': foreign_data[0]['foreign_sell'],
            'avg_net': avg_net,
            'avg_7_days': avg_7_days,
            'avg_30_days': avg_30_days,
            'spike_ratio': spike_ratio,
            'current_price': foreign_data[0]['price'],
            'data_points': len(foreign_data),
            'is_net_positive': latest_net > 0,
            'trend_7vs30': avg_7_days > avg_30_days
        }
        
        return analysis, None
        
    except Exception as e:
        logger.error(f"Error in analyze_stock_foreign: {e}")
        return None, "Error saat menganalisis foreign flow"

def get_stock_margin_data(stock_code):
    """Get margin data for specific stock"""
    try:
        viewer.load_margin_files()
        if viewer.margin_df is None:
            return None, "Data margin tidak tersedia"
        
        # Search for stock in margin data
        # This implementation depends on the actual structure of margin_df
        # Assuming it has columns like 'kode', 'margin_buy', 'margin_sell', etc.
        
        if 'Kode Saham' in viewer.margin_df.columns:
            stock_margin = viewer.margin_df[viewer.margin_df['Kode Saham'].str.upper() == stock_code.upper()]
            
            if stock_margin.empty:
                return None, f"Saham {stock_code} tidak terdaftar dalam margin trading"
            
            # Get the most recent margin data
            margin_info = stock_margin.iloc[0]
            
            analysis = {
                'stock_code': stock_code,
                'is_marginable': True,
                'margin_data': margin_info.to_dict()
            }
            
            return analysis, None
        else:
            return None, "Format data margin tidak dikenali"
            
    except Exception as e:
        logger.error(f"Error in get_stock_margin_data: {e}")
        return None, "Error saat menganalisis data margin"

def get_foreign_summary_by_days(stock_code):
    """Get foreign flow summary for different time periods"""
    try:
        viewer.load_watchlist_data()
        summary = viewer.get_foreign_summary_by_days(stock_code)
        return summary
    except Exception as e:
        logger.error(f"Error getting foreign summary: {e}")
        return None

@is_authorized_user 
@spy      
@vip
@with_rate_limit      
async def saham_commanduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified command handler for stock analysis with specific stock code"""
    
    start_time = time.time()
    
    # Parse command
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Masukkan kode saham.\nContoh: `/saham BBCA`", 
            parse_mode='Markdown'
        )
        return
    
    stock_code = parts[1].upper()
    
    # Send initial processing message
    processing_msg = await update.message.reply_text(f"🔄 Menganalisis data untuk {stock_code}... Mohon tunggu...")
    
    try:
        # Header message
        header_message = f"📊 **ANALISIS LENGKAP: {stock_code}**\n"
        header_message += f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        header_message += "="*35
        
        await update.message.reply_text(header_message, parse_mode='Markdown')
        
        # 1. VOLUME ANALYSIS
        await update.message.reply_text("📊 Menganalisis VSA...")
        volume_analysis, vol_error = analyze_stock_volume(stock_code)
        
        if volume_analysis:
            vol_message = f"```\n📈 VSA ANALYSIS - {stock_code}\n"
            vol_message += "="*40 + "\n"
            vol_message += f"Harga Saat Ini    : {volume_analysis['current_price']:>12,.0f}\n"
            vol_message += f"Volume Hari Ini   : {volume_analysis['vol_today']:>12,.0f}\n"
            vol_message += f"Rata-rata 7 Hari  : {volume_analysis['avg_7_days']:>12,.0f}\n"
            vol_message += f"Rata-rata 30 Hari : {volume_analysis['avg_30_days']:>12,.0f}\n"
            vol_message += f"VSA Score         : {volume_analysis['vol_spike']:>12.2f}\n"
            vol_message += "="*40 + "\n"
            vol_message += f"Status Trending   : {'✅ YA' if volume_analysis['is_trending'] else '❌ TIDAK'}\n"
            vol_message += "```\n"
            
            # Add interpretation
            if volume_analysis['vol_spike'] >= 2:
                vol_message += "🚀 **VSA tinggi! **"
            elif volume_analysis['is_trending']:
                vol_message += "📈 **VSA dalam tren naik**"
            else:
                vol_message += "😐 **VSA dalam kondisi normal**"
            
            await update.message.reply_text(vol_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ VSA: {vol_error}")
        
        # 2. FOREIGN FLOW ANALYSIS
        await update.message.reply_text("🌍 Menganalisis Foreign Flow...")
        foreign_analysis, foreign_error = analyze_stock_foreign(stock_code)
        
        if foreign_analysis:
            foreign_message = f"```\n🌍 FOREIGN FLOW ANALYSIS - {stock_code}\n"
            foreign_message += "="*45 + "\n"
            foreign_message += f"Net Foreign Hari Ini (lembar saham)  : {foreign_analysis['latest_net']:>+15,.0f}\n"
            foreign_message += "="*45 + "\n"
            foreign_message += f"Rata-rata Net 7 Hari  : {foreign_analysis['avg_7_days']:>+15,.0f}\n"
            foreign_message += f"Rata-rata Net 30 Hari : {foreign_analysis['avg_30_days']:>+15,.0f}\n"
            foreign_message += "="*45 + "\n"
            
            # Format spike ratio
            if foreign_analysis['spike_ratio'] == float('inf'):
                spike_str = "∞+"
            elif foreign_analysis['spike_ratio'] == float('-inf'):
                spike_str = "∞-"
            else:
                spike_str = f"{foreign_analysis['spike_ratio']:+.2f}x"
            
            foreign_message += f"FSA Ratio          : {spike_str:>15}\n"
            foreign_message += f"Tren 7 vs 30 Hari     : {'📈 UP' if foreign_analysis['trend_7vs30'] else '📉 DOWN':>15}\n"
            foreign_message += "```\n"
            
            # Add interpretation
            if foreign_analysis['is_net_positive']:
                if abs(foreign_analysis['spike_ratio']) >= 2.5:
                    foreign_message += "🚀 **FSA tinggi**"
                else:
                    foreign_message += "💚 **FSA positif**"
            else:
                foreign_message += "🔴 **FSA selling**"
            
            await update.message.reply_text(foreign_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Foreign Flow: {foreign_error}")
        
        # 3. FOREIGN SUMMARY BY PERIODS
        await update.message.reply_text("📊 Menganalisis FSA...")
        foreign_summary = get_foreign_summary_by_days(stock_code)
        
        if foreign_summary:
            summary_message = f"```\n📊 FOREIGN FLOW SUMMARY - {stock_code}\n"
            summary_message += "="*50 + "\n"
            summary_message += f"{'Period':>6} | {'Buy':>12} | {'Sell':>12} | {'Net':>13}\n"
            summary_message += "="*50 + "\n"
            
            for days, buy, sell, net in foreign_summary:
                summary_message += f"{days:>6} | {buy:>12,.0f} | {sell:>12,.0f} | {net:>+13,.0f}\n"
            
            summary_message += "```"
            await update.message.reply_text(summary_message, parse_mode='Markdown')
        
        # 4. MARGIN ANALYSIS
        await update.message.reply_text("💰 Menganalisis Margin Trading...")
        margin_analysis, margin_error = get_stock_margin_data(stock_code)
        
        if margin_analysis:
            margin_message = f"```\n💰 MARGIN TRADING - {stock_code}\n"
            margin_message += "="*30 + "\n"
            margin_message += f"Status: Marginable ✅\n"          
            margin_message += "```"
            await update.message.reply_text(margin_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ Margin: {margin_error}")
        
        # 5. CHART GENERATION
        try:
            await update.message.reply_text("📈 Membuat chart margin...")
            chart_buffer = viewer.create_margin_charts(stock_code)
            if chart_buffer:
                await update.message.reply_photo(
                    photo=chart_buffer,
                    caption=f"📊 Margin Trading Chart - {stock_code}"
                )
        except Exception as e:
            logger.error(f"Error creating chart: {e}")
            
        # 6. Holding
        await update.message.reply_text("👥 Menganalisis Holdings Summary...")
        try:
            viewer.load_all_excel_files()
            if viewer.combined_df is not None:
                df = viewer.search_stock(stock_code)
                if df is not None and not df.empty:
                    # Load harga penutupan dari folder foreign
                    folder_path = "/home/ec2-user/database/foreign"
                    excel_files = sorted(glob.glob(os.path.join(folder_path, "*.xlsx")), reverse=True)
                    if excel_files:
                        harga_data = pd.read_excel(excel_files[0])
                        harga_dict = dict(zip(harga_data['Kode Saham'].str.upper(), harga_data['Penutupan']))
                        closing_price = harga_dict.get(stock_code)
                        
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
                        await update.message.reply_text("❌ Holdings: Tidak ada file harga penutupan")
                else:
                    await update.message.reply_text(f"❌ Holdings: Tidak ada data kepemilikan untuk {stock_code}")
            else:
                await update.message.reply_text("❌ Holdings: Tidak ada data kepemilikan")
        except Exception as e:
            logger.error(f"Error in holdings analysis: {e}")
            await update.message.reply_text(f"❌ Holdings: Error saat menganalisis kepemilikan")
            
        # 7. SECTOR ANALYSIS - NEW SECTION
        await update.message.reply_text("🏢 Menganalisis Data Sektor...")
        sector_analysis, sector_error = get_stock_sector_data(stock_code)
        
        if sector_analysis:
            sector_message = f"```\n🏢 SECTOR INFORMATION - {stock_code}\n"
            sector_message += "="*40 + "\n"
            sector_message += f"Sektor            : {sector_analysis['sector']}\n"
            
            # Format tanggal pencatatan if available
            if pd.notna(sector_analysis['tanggal_pencatatan']):
                if isinstance(sector_analysis['tanggal_pencatatan'], str):
                    sector_message += f"Tanggal Pencatatan: {sector_analysis['tanggal_pencatatan']}\n"
                else:
                    try:
                        # Try to format as date if it's a datetime object
                        formatted_date = pd.to_datetime(sector_analysis['tanggal_pencatatan']).strftime('%d/%m/%Y')
                        sector_message += f"Tanggal Pencatatan: {formatted_date}\n"
                    except:
                        sector_message += f"Tanggal Pencatatan: {sector_analysis['tanggal_pencatatan']}\n"
            
            # Format papan pencatatan if available
            if pd.notna(sector_analysis['papan_pencatatan']):
                sector_message += f"Papan Pencatatan  : {sector_analysis['papan_pencatatan']}\n"
            
            sector_message += "```"
            await update.message.reply_text(sector_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ Sektor: {sector_error}")
        
        # FINAL SUMMARY
        summary_msg = f"✅ **RINGKASAN ANALISIS {stock_code}**\n\n"
        
        if sector_analysis:
            summary_msg += f"🏢 Sektor: {sector_analysis['sector']}\n"
        
        if volume_analysis:
            summary_msg += f"📈 VSA Score: {volume_analysis['vol_spike']:.2f} "
            summary_msg += f"({'🚀 HIGH' if volume_analysis['vol_spike'] >= 2.2 else '😐 NORMAL'})\n"
        
        if foreign_analysis:
            summary_msg += f"🌍 FSA: {foreign_analysis['latest_net']:+,.0f} "
            summary_msg += f"({'💚 BUY' if foreign_analysis['is_net_positive'] else '🔴 SELL'})\n"
        
        if margin_analysis:
            summary_msg += f"💰 Margin: ✅ Available\n"
        else:
            summary_msg += f"💰 Margin: ❌ Not Available\n"
        
        end_time = time.time()
        processing_duration = end_time - start_time
        summary_msg += f"\n⏱️ Analisis selesai dalam {processing_duration:.2f} detik"
        
        await update.message.reply_text(summary_msg, parse_mode='Markdown')
        
        # Delete processing message
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in saham_command: {e}")
        await processing_msg.edit_text(f"❌ Terjadi error: {str(e)}")
    
    finally:
        # Clean up memory
        viewer.margin_df = None
        viewer.combined_df = None
        plt.close('all')
        import gc
        gc.collect()