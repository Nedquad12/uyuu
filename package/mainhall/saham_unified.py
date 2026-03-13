from imporh import *
import sys
import time
import asyncio
from datetime import datetime
import pytz
from cache import read_or_cache
from excel_reader import get_excel_files, get_stock_sector_data
from ma_tracker import ma_tracker
from holdinghand import data_cache, get_holdings_summary_fast
sys.path.append("/home/ec2-user/package/machine")
from utama import TelegramStockDataViewer

# WIB timezone
WIB = pytz.timezone('Asia/Jakarta')

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

async def run_with_timeout(coro, timeout=5):
    """Run coroutine with timeout"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Operation timed out after {timeout}s")
        return None, "Timeout"
    except Exception as e:
        logger.error(f"Error in run_with_timeout: {e}")
        return None, str(e)

async def analyze_stock_volume_async(stock_code):
    """Async wrapper for analyze_stock_volume"""
    return analyze_stock_volume(stock_code)

def analyze_stock_volume(stock_code):
    """Analyze volume for specific stock - DIRECT from CACHE"""
    try:
        import os
        import glob
        import json
        from datetime import datetime
        
        cache_dir = "/home/ec2-user/database/cache"
        cache_files = glob.glob(os.path.join(cache_dir, "*.txt"))
        
        file_with_dates = []
        for cache_file in cache_files:
            filename = os.path.basename(cache_file)
            date_str = filename.replace('.txt', '')
            try:
                date_obj = datetime.strptime(date_str, '%d%m%y')
                file_with_dates.append((cache_file, date_obj))
            except:
                continue
        
        file_with_dates.sort(key=lambda x: x[1], reverse=True)
        
        if len(file_with_dates) < 7:
            return None, "Tidak cukup data untuk analisis (minimal 7 file)"
        
        file_with_dates = file_with_dates[:60]
        volume_data = []
        
        for cache_file, date_obj in file_with_dates:
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                kode_saham = data.get('kode_saham', [])[1:]
                volume = data.get('volume', [])[1:]
                penutupan = data.get('penutupan', [])[1:]
                
                if not kode_saham or not volume or not penutupan:
                    continue
                
                try:
                    idx = kode_saham.index(stock_code)
                except ValueError:
                    continue
                
                vol = volume[idx] if isinstance(volume[idx], (int, float)) else 0
                price = penutupan[idx] if isinstance(penutupan[idx], (int, float)) else 0
                
                volume_data.append({
                    'date': date_obj,
                    'volume': vol,
                    'price': price
                })
                
            except Exception as e:
                logger.error(f"Error reading cache file {cache_file}: {e}")
                continue
        
        if len(volume_data) < 7:
            return None, f"Tidak cukup data untuk {stock_code} (ditemukan {len(volume_data)} hari)"
        
        volumes = [item['volume'] for item in volume_data]
        vol_today = volumes[0]
        avg_7_days = sum(volumes[:7]) / 7
        avg_30_days = sum(volumes[:min(30, len(volumes))]) / min(30, len(volumes))
        max_days = min(len(volumes), 60)
        avg_60_days = sum(volumes[:max_days]) / max_days
        
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
            'spike_7vs30': spike_7vs30,
            'spike_7vs60': spike_7vs60,
            'vol_spike': vol_spike,
            'current_price': volume_data[0]['price'],
            'data_points': len(volume_data),
            'is_trending': avg_7_days > avg_60_days and avg_7_days > avg_30_days and vol_today > avg_7_days
        }
        
        return analysis, None
        
    except Exception as e:
        logger.error(f"Error in analyze_stock_volume: {e}")
        return None, "Error saat menganalisis volume"

async def analyze_stock_foreign_async(stock_code):
    """Async wrapper for analyze_stock_foreign"""
    return analyze_stock_foreign(stock_code)

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
            
            stock_row = df[df['kode_saham'] == stock_code]
            if not stock_row.empty:
                row_data = stock_row.iloc[0]
                foreign_buy = row_data['foreign_buy']
                foreign_sell = row_data['foreign_sell']
                foreign_net = foreign_buy - foreign_sell
                foreign_data.append({
                    'date': file_info['date'],
                    'foreign_buy': foreign_buy,
                    'foreign_sell': foreign_sell,
                    'foreign_net': foreign_net,
                    'price': row_data['penutupan']
                })
        
        if len(foreign_data) < 2:
            return None, f"Tidak cukup data foreign untuk {stock_code}"
        
        foreign_data.sort(key=lambda x: x['date'], reverse=True)
        
        net_flows = [item['foreign_net'] for item in foreign_data]
        latest_net = net_flows[0]
        avg_net = sum(net_flows) / len(net_flows)
        
        if avg_net != 0:
            spike_ratio = latest_net / avg_net
        else:
            if latest_net > 0:
                spike_ratio = float('inf')
            elif latest_net < 0:
                spike_ratio = float('-inf')
            else:
                spike_ratio = 0
        
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

async def get_stock_ma_data_async(stock_code):
    """Async wrapper for get_stock_ma_data"""
    return get_stock_ma_data(stock_code)

def get_stock_ma_data(stock_code):
    """Get MA data for specific stock from ma_tracker cache"""
    try:
        if stock_code.upper() not in ma_tracker.ma_cache:
            return None, f"Data MA untuk {stock_code} tidak tersedia"
        
        stock_data = ma_tracker.ma_cache[stock_code.upper()]
        
        ma_periods = [20, 60, 120, 200]
        ma_analysis = {
            'stock_code': stock_code,
            'current_price': stock_data['close'],
            'mas': {}
        }
        
        for period in ma_periods:
            if period in stock_data['mas']:
                ma_value = stock_data['mas'][period]
                diff_pct = stock_data['mas'].get(f'{period}_diff', 0)
                
                if diff_pct > 0:
                    position = "ABOVE"
                elif diff_pct < 0:
                    position = "BELOW"
                else:
                    position = "AT"
                
                ma_analysis['mas'][period] = {
                    'value': ma_value,
                    'diff_pct': diff_pct,
                    'position': position
                }
            else:
                ma_analysis['mas'][period] = None
        
        return ma_analysis, None
        
    except Exception as e:
        logger.error(f"Error in get_stock_ma_data: {e}")
        return None, "Error saat menganalisis MA"

async def get_stock_margin_data_async(stock_code):
    """Async wrapper for get_stock_margin_data"""
    return get_stock_margin_data(stock_code)

def get_stock_margin_data(stock_code):
    """Get margin data for specific stock"""
    try:
        viewer.load_margin_files()
        if viewer.margin_df is None:
            return None, "Data margin tidak tersedia"
        
        if 'Kode Saham' in viewer.margin_df.columns:
            stock_margin = viewer.margin_df[viewer.margin_df['Kode Saham'].str.upper() == stock_code.upper()]
            
            if stock_margin.empty:
                return None, f"Saham {stock_code} tidak terdaftar dalam margin trading"
            
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

async def get_foreign_summary_by_days_async(stock_code):
    """Async wrapper for get_foreign_summary_by_days"""
    return get_foreign_summary_by_days(stock_code)

def get_foreign_summary_by_days(stock_code):
    """Get foreign flow summary for different time periods - DIRECT from CACHE"""
    try:
        import os
        import glob
        import json
        from datetime import datetime
        
        cache_dir = "/home/ec2-user/database/cache"
        cache_files = glob.glob(os.path.join(cache_dir, "*.txt"))
        
        file_with_dates = []
        for cache_file in cache_files:
            filename = os.path.basename(cache_file)
            date_str = filename.replace('.txt', '')
            try:
                date_obj = datetime.strptime(date_str, '%d%m%y')
                file_with_dates.append((cache_file, date_obj))
            except:
                continue
        
        file_with_dates.sort(key=lambda x: x[1], reverse=True)
        cache_files = [f[0] for f in file_with_dates]
        
        if len(cache_files) < 2:
            return None
        
        cache_files = cache_files[:60]
        foreign_data = []
        
        for cache_file in cache_files:
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                
                kode_saham = data.get('kode_saham', [])[1:]
                foreign_buy = data.get('foreign_buy', [])[1:]
                foreign_sell = data.get('foreign_sell', [])[1:]
                
                if not kode_saham or not foreign_buy or not foreign_sell:
                    continue
                
                try:
                    idx = kode_saham.index(stock_code)
                except ValueError:
                    continue
                
                buy = foreign_buy[idx] if isinstance(foreign_buy[idx], (int, float)) else 0
                sell = foreign_sell[idx] if isinstance(foreign_sell[idx], (int, float)) else 0
                net = buy - sell
                
                filename = os.path.basename(cache_file)
                date_str = filename.replace('.txt', '')
                try:
                    date_obj = datetime.strptime(date_str, '%d%m%y')
                except:
                    continue
                
                foreign_data.append({
                    'date': date_obj,
                    'buy': buy,
                    'sell': sell,
                    'net': net
                })
                
            except Exception as e:
                logger.error(f"Error reading cache file {cache_file}: {e}")
                continue
        
        if len(foreign_data) < 2:
            return None
        
        foreign_data.sort(key=lambda x: x['date'], reverse=True)
        
        periods = [
            ('1H', 1),
            ('5H', 5),
            ('1B', 22),
            ('3B', min(60, len(foreign_data))),
        ]
        
        summary = []
        for period_name, days in periods:
            if days > len(foreign_data):
                days = len(foreign_data)
            
            period_data = foreign_data[:days]
            total_buy = sum(item['buy'] for item in period_data)
            total_sell = sum(item['sell'] for item in period_data)
            total_net = sum(item['net'] for item in period_data)
            
            summary.append((period_name, total_buy, total_sell, total_net))
        
        return summary
        
    except Exception as e:
        logger.error(f"Error getting foreign summary: {e}")
        return None

async def get_stock_sector_data_async(stock_code):
    """Async wrapper for get_stock_sector_data"""
    return get_stock_sector_data(stock_code)

@is_authorized_user 
@spy      
@vip       
async def saham_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified command handler for stock analysis with specific stock code"""
    
    start_time = time.time()
    
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ Masukkan kode saham.\nContoh: `/saham BBCA`", 
            parse_mode='Markdown'
        )
        return
    
    stock_code = parts[1].upper()
    
    processing_msg = await update.message.reply_text(f"🔄 Menganalisis data untuk {stock_code}... Mohon tunggu...")
    
    try:
        # Get WIB time
        now_wib = datetime.now(WIB)
        
        # Header message
        header_message = f"📊 **ANALISIS LENGKAP: {stock_code}**\n"
        header_message += f"🕐 {now_wib.strftime('%d/%m/%Y %H:%M')} WIB\n"
        header_message += "="*35
        
        await update.message.reply_text(header_message, parse_mode='Markdown')
        await asyncio.sleep(0.4)
        
        # 1. VOLUME ANALYSIS
        result = await run_with_timeout(analyze_stock_volume_async(stock_code), timeout=5)
        if result:
            volume_analysis, vol_error = result
        else:
            volume_analysis, vol_error = None, "Timeout"
        
        if volume_analysis:
            vol_message = f"```\n📈 VOLUME ANALYSIS - {stock_code}\n"
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
            vol_message += f"Data Points       : {volume_analysis['data_points']} hari\n"
            vol_message += f"Status Trending   : {'✅ YA' if volume_analysis['is_trending'] else '❌ TIDAK'}\n"
            vol_message += "```\n"
            
            if volume_analysis['vol_spike'] >= 2.2:
                vol_message += "🚀 **Volume spike tinggi!**"
            elif volume_analysis['is_trending']:
                vol_message += "📈 **Volume dalam tren naik**"
            else:
                vol_message += "😐 **Volume dalam kondisi normal**"
            
            await update.message.reply_text(vol_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Volume: {vol_error}")
        
        await asyncio.sleep(0.4)
        
        # 2. FOREIGN FLOW ANALYSIS
        result = await run_with_timeout(analyze_stock_foreign_async(stock_code), timeout=5)
        if result:
            foreign_analysis, foreign_error = result
        else:
            foreign_analysis, foreign_error = None, "Timeout"
        
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
        
        await asyncio.sleep(0.4)
        
        # 3. MOVING AVERAGE ANALYSIS
        result = await run_with_timeout(get_stock_ma_data_async(stock_code), timeout=5)
        if result:
            ma_analysis, ma_error = result
        else:
            ma_analysis, ma_error = None, "Timeout"
        
        if ma_analysis:
            ma_message = f"```\n📊 MOVING AVERAGE ANALYSIS - {stock_code}\n"
            ma_message += "="*50 + "\n"
            ma_message += f"Harga Saat Ini: {ma_analysis['current_price']:,.0f}\n"
            ma_message += "="*50 + "\n"
            ma_message += f"{'MA':<6} {'Value':<10} {'Diff %':<10} {'Position':<8}\n"
            ma_message += "-"*50 + "\n"
            
            ma_periods = [20, 60, 120, 200]
            for period in ma_periods:
                ma_data = ma_analysis['mas'].get(period)
                
                if ma_data is None:
                    ma_message += f"MA{period:<3} {'NaN':<10} {'NaN':<10} {'N/A':<8}\n"
                else:
                    value_str = f"{ma_data['value']:,.0f}"
                    diff_str = f"{ma_data['diff_pct']:+.2f}%"
                    position = ma_data['position']
                    
                    ma_message += f"MA{period:<3} {value_str:<10} {diff_str:<10} {position:<8}\n"
            
            ma_message += "```"
            
            all_above = all(
                ma_analysis['mas'].get(p) and ma_analysis['mas'][p]['position'] == "ABOVE" 
                for p in ma_periods if ma_analysis['mas'].get(p) is not None
            )
            
            if all_above:
                ma_message += "\n💚 **Harga di atas semua MA - Strong uptrend!**"
            elif ma_analysis['mas'].get(20) and ma_analysis['mas'][20]['position'] == "ABOVE":
                ma_message += "\n🟢 **Harga di atas MA20 - Short term bullish**"
            else:
                ma_message += "\n📊 **Monitor pergerakan MA untuk konfirmasi trend**"
            
            await update.message.reply_text(ma_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ MA: {ma_error}")
        
        await asyncio.sleep(0.4)
        
        # 4. FOREIGN SUMMARY BY PERIODS
        result = await run_with_timeout(get_foreign_summary_by_days_async(stock_code), timeout=5)
        if result:
            foreign_summary = result
        else:
            foreign_summary = None
        
        if foreign_summary:
            summary_message = f"```\n📊 FOREIGN FLOW SUMMARY - {stock_code}\n"
            summary_message += "="*50 + "\n"
            summary_message += f"{'Period':>6} | {'Buy':>12} | {'Sell':>12} | {'Net':>13}\n"
            summary_message += "="*50 + "\n"
            
            for days, buy, sell, net in foreign_summary:
                summary_message += f"{days:>6} | {buy:>12,.0f} | {sell:>12,.0f} | {net:>+13,.0f}\n"
            
            summary_message += "```"
            await update.message.reply_text(summary_message, parse_mode='Markdown')
        
        await asyncio.sleep(0.4)
        
        # 5. MARGIN ANALYSIS
        result = await run_with_timeout(get_stock_margin_data_async(stock_code), timeout=5)
        if result:
            margin_analysis, margin_error = result
        else:
            margin_analysis, margin_error = None, "Timeout"
        
        if margin_analysis:
            margin_message = f"```\n💰 MARGIN TRADING - {stock_code}\n"
            margin_message += "="*30 + "\n"
            margin_message += f"Status: Marginable ✅\n"
            margin_message += "```"
            await update.message.reply_text(margin_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ Margin: {margin_error}")
        
        await asyncio.sleep(0.4)
        
        # 6. CHART GENERATION
        try:
            chart_buffer = viewer.create_margin_charts(stock_code)
            if chart_buffer:
                await update.message.reply_photo(
                    photo=chart_buffer,
                    caption=f"📊 Margin Trading Chart - {stock_code}"
                )
                await asyncio.sleep(0.4)
        except Exception as e:
            logger.error(f"Error creating chart: {e}")
            
        # 7. HOLDINGS
        try:
            holdings_result = await asyncio.wait_for(
                get_holdings_summary_fast(stock_code), 
                timeout=5
            )
            holdings_message, holdings_error = holdings_result
            
            if holdings_message:
                await update.message.reply_text(holdings_message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Holdings: {holdings_error}")
            
            await asyncio.sleep(0.4)
                
        except asyncio.TimeoutError:
            await update.message.reply_text(f"❌ Holdings: Timeout")
            await asyncio.sleep(0.4)
        except Exception as e:
            logger.error(f"Error in holdings analysis: {e}")
            await update.message.reply_text(f"❌ Holdings: Error saat menganalisis kepemilikan")
            await asyncio.sleep(0.4)
        
        # 8. SECTOR ANALYSIS
        result = await run_with_timeout(get_stock_sector_data_async(stock_code), timeout=5)
        if result:
            sector_analysis, sector_error = result
        else:
            sector_analysis, sector_error = None, "Timeout"
        
        if sector_analysis:
            sector_message = f"```\n🏢 SECTOR INFORMATION - {stock_code}\n"
            sector_message += "="*40 + "\n"
            sector_message += f"Sektor            : {sector_analysis['sector']}\n"
            
            if pd.notna(sector_analysis['tanggal_pencatatan']):
                if isinstance(sector_analysis['tanggal_pencatatan'], str):
                    sector_message += f"Tanggal Pencatatan: {sector_analysis['tanggal_pencatatan']}\n"
                else:
                    try:
                        formatted_date = pd.to_datetime(sector_analysis['tanggal_pencatatan']).strftime('%d/%m/%Y')
                        sector_message += f"Tanggal Pencatatan: {formatted_date}\n"
                    except:
                        sector_message += f"Tanggal Pencatatan: {sector_analysis['tanggal_pencatatan']}\n"
            
            if pd.notna(sector_analysis['papan_pencatatan']):
                sector_message += f"Papan Pencatatan  : {sector_analysis['papan_pencatatan']}\n"
            
            sector_message += "```"
            await update.message.reply_text(sector_message, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ Sektor: {sector_error}")
        
        await asyncio.sleep(0.4)
        
        # FINAL SUMMARY WITH SECTOR
        summary_msg = f"✅ **RINGKASAN ANALISIS {stock_code}**\n\n"
        
        if sector_analysis:
            summary_msg += f"🏢 Sektor: {sector_analysis['sector']}\n"
        
        if volume_analysis:
            summary_msg += f"📈 VSA Score: {volume_analysis['vol_spike']:.2f} "
            summary_msg += f"({'🚀 HIGH' if volume_analysis['vol_spike'] >= 2.2 else '😐 NORMAL'})\n"
        
        if foreign_analysis:
            summary_msg += f"🌍 Net Foreign: {foreign_analysis['latest_net']:+,.0f} "
            summary_msg += f"({'💚 BUY' if foreign_analysis['is_net_positive'] else '🔴 SELL'})\n"
            
        if ma_analysis:
           above_count = sum(1 for p in [20, 60, 120, 200] 
                            if ma_analysis['mas'].get(p) and ma_analysis['mas'][p]['position'] == "ABOVE")
           summary_msg += f"📊 MA Position: {above_count}/4 Above\n"
        
        if margin_analysis:
            summary_msg += f"💰 Margin: ✅ Available\n"
        else:
            summary_msg += f"💰 Margin: ❌ Not Available\n"
        
        end_time = time.time()
        processing_duration = end_time - start_time
        summary_msg += f"\n⏱️ Analisis selesai dalam {processing_duration:.2f} detik"
        
        await update.message.reply_text(summary_msg, parse_mode='Markdown')
        
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in saham_command: {e}")
        await processing_msg.edit_text(f"❌ Terjadi error: {str(e)}")
    
    finally:
        viewer.margin_df = None
        viewer.combined_df = None
        plt.close('all')
        import gc
        gc.collect()