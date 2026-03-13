import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import logging
from imporh import*

logger = logging.getLogger(__name__)

class MSTracker:
    def __init__(self, cache_dir="/home/ec2-user/database/cache"):
        self.cache_dir = cache_dir
        self.ram_cache = {}  # Cache untuk menyimpan data di RAM
        self.ms_cache = {}   # Cache untuk menyimpan hasil perhitungan MACD & Stochastic
        self.files_info = []  # Info file yang tersedia
        self.last_reload = None  # Timestamp reload terakhir
        
        logger.info(f"MSTracker initialized. Use /reload4 to load data.")
        
    def parse_filename_date(self, filename):
        """Parse date from filename format ddmmyy.txt"""
        try:
            date_str = filename.replace('.txt', '')
            if len(date_str) == 6:
                day = int(date_str[:2])
                month = int(date_str[2:4])
                year = 2000 + int(date_str[4:6])
                return datetime(year, month, day)
        except ValueError:
            pass
        return None
    
    def get_available_files(self):
        """Get all available cache files sorted by date (newest first)"""
        files = []
        if not os.path.exists(self.cache_dir):
            return files
            
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.txt'):
                file_date = self.parse_filename_date(filename)
                if file_date:
                    files.append({
                        'filename': filename,
                        'date': file_date,
                        'path': os.path.join(self.cache_dir, filename)
                    })
        
        # Sort by date, newest first
        files.sort(key=lambda x: x['date'], reverse=True)
        return files
    
    def load_stock_data(self, file_path):
        """Load stock data from JSON txt file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract stock codes, closing prices, volumes, highs, lows
            kode_saham = data.get('kode_saham', [])
            penutupan = data.get('penutupan', [])
            volume = data.get('volume', [])
            tertinggi = data.get('tertinggi', [])
            terendah = data.get('terendah', [])
            
            # Skip header (index 0) and create dataframe
            stocks = []
            for i in range(1, len(kode_saham)):
                if (i < len(penutupan) and i < len(volume) and 
                    i < len(tertinggi) and i < len(terendah) and
                    kode_saham[i] and penutupan[i] and volume[i] and
                    tertinggi[i] and terendah[i]):
                    try:
                        stocks.append({
                            'kode': str(kode_saham[i]).strip().upper(),
                            'close': float(penutupan[i]),
                            'high': float(tertinggi[i]),
                            'low': float(terendah[i]),
                            'volume': int(volume[i])
                        })
                    except (ValueError, TypeError):
                        continue
            
            return pd.DataFrame(stocks)
            
        except Exception as e:
            logger.error(f"Error loading stock data from {file_path}: {e}")
            return pd.DataFrame()
    
    def calculate_ema(self, prices, period):
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        # Convert to pandas Series for EMA calculation
        series = pd.Series(prices)
        ema = series.ewm(span=period, adjust=False).mean()
        return ema.iloc[-1]
    
    def calculate_macd(self, prices):
        """Calculate MACD (12, 26, 9)"""
        if len(prices) < 35:  # Need at least 26 + 9 days
            return None, None
        
        # Calculate EMAs
        series = pd.Series(prices)
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        
        # MACD Line = EMA12 - EMA26
        macd_line = ema12 - ema26
        
        # Signal Line = EMA9 of MACD Line
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        return macd_line.iloc[-1], signal_line.iloc[-1]
    
    def calculate_stochastic(self, highs, lows, closes, k_period=14, d_period=3):
        """Calculate Stochastic Oscillator (%K and %D)"""
        if len(closes) < k_period:
            return None, None
        
        # %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
        lowest_low = min(lows[-k_period:])
        highest_high = max(highs[-k_period:])
        
        if highest_high == lowest_low:
            return None, None
        
        current_close = closes[-1]
        k_value = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
        
        # %D = SMA of %K (need to calculate multiple %K values)
        k_values = []
        for i in range(len(closes) - k_period + 1):
            window_closes = closes[i:i+k_period]
            window_highs = highs[i:i+k_period]
            window_lows = lows[i:i+k_period]
            
            low = min(window_lows)
            high = max(window_highs)
            
            if high != low:
                k = ((window_closes[-1] - low) / (high - low)) * 100
                k_values.append(k)
        
        if len(k_values) < d_period:
            return k_value, None
        
        # %D is the moving average of %K
        d_value = np.mean(k_values[-d_period:])
        
        return k_value, d_value
    
    def get_historical_data(self, stock_code, days_needed=50):
        """Get historical closing prices, highs, lows for a stock dari RAM cache"""
        if not self.files_info:
            return [], [], []
        
        closes = []
        highs = []
        lows = []
        files_to_check = min(days_needed, len(self.files_info))
        
        for i in range(files_to_check):
            file_info = self.files_info[i]
            filename = file_info['filename']
            
            # Ambil dari RAM cache
            df = self.ram_cache.get(filename, pd.DataFrame())
            if not df.empty:
                stock_row = df[df['kode'] == stock_code.upper()]
                if not stock_row.empty:
                    closes.append(stock_row.iloc[0]['close'])
                    highs.append(stock_row.iloc[0]['high'])
                    lows.append(stock_row.iloc[0]['low'])
        
        # Reverse to get chronological order (oldest first)
        return closes[::-1], highs[::-1], lows[::-1]
    
    def calculate_all_ms(self):
        """Pre-calculate semua MACD & Stochastic untuk semua saham"""
        logger.info("Pre-calculating all MACD & Stochastic values...")
        
        # Clear existing MS cache
        self.ms_cache.clear()
        
        if not self.files_info or not self.ram_cache:
            return
        
        # Need at least 2 days for cross detection
        if len(self.files_info) < 2:
            logger.warning("Need at least 2 days of data for cross detection")
            return
        
        # Get latest data untuk daftar semua saham
        latest_filename = self.files_info[0]['filename']
        yesterday_filename = self.files_info[1]['filename']
        
        latest_df = self.ram_cache.get(latest_filename, pd.DataFrame())
        yesterday_df = self.ram_cache.get(yesterday_filename, pd.DataFrame())
        
        if latest_df.empty or yesterday_df.empty:
            return
        
        total_stocks = len(latest_df)
        processed = 0
        successful = 0
        
        for _, row in latest_df.iterrows():
            stock_code = row['kode']
            current_price = row['close']
            volume = row['volume']
            
            # Get historical data (50 days should be enough for both indicators)
            closes, highs, lows = self.get_historical_data(stock_code, 50)
            
            if len(closes) < 35:  # Minimum for MACD
                processed += 1
                continue
            
            stock_ms = {
                'kode': stock_code,
                'close': current_price,
                'volume': volume,
                'value': current_price * volume,
                'signals': []
            }
            
            # Calculate MACD today
            macd_today, signal_today = self.calculate_macd(closes)
            
            # Calculate MACD yesterday
            macd_yesterday, signal_yesterday = self.calculate_macd(closes[:-1])
            
            # Check MACD cross
            if macd_today and signal_today and macd_yesterday and signal_yesterday:
                # Golden Cross: MACD crosses above Signal
                if macd_today > signal_today and macd_yesterday <= signal_yesterday:
                    stock_ms['signals'].append('M+')
                # Death Cross: MACD crosses below Signal
                elif macd_today < signal_today and macd_yesterday >= signal_yesterday:
                    stock_ms['signals'].append('M-')
            
            # Calculate Stochastic today
            k_today, d_today = self.calculate_stochastic(highs, lows, closes)
            
            # Calculate Stochastic yesterday
            k_yesterday, d_yesterday = self.calculate_stochastic(highs[:-1], lows[:-1], closes[:-1])
            
            # Check Stochastic cross
            if k_today and d_today and k_yesterday and d_yesterday:
                # Golden Cross: %K crosses above %D
                if k_today > d_today and k_yesterday <= d_yesterday:
                    if k_today > 80:
                        stock_ms['signals'].append('S+❤️')
                    elif k_today < 20:
                        stock_ms['signals'].append('S+💚')
                    else:
                        stock_ms['signals'].append('S+')
                # Death Cross: %K crosses below %D
                elif k_today < d_today and k_yesterday >= d_yesterday:
                    if k_today > 80:
                        stock_ms['signals'].append('S-❤️')
                    elif k_today < 20:
                        stock_ms['signals'].append('S-💚')
                    else:
                        stock_ms['signals'].append('S-')
            
            # Simpan ke MS cache jika ada signal
            if stock_ms['signals']:
                self.ms_cache[stock_code] = stock_ms
                successful += 1
            
            processed += 1
            # Log progress setiap 500 saham
            if processed % 500 == 0:
                logger.info(f"Processed MS for {processed}/{total_stocks} stocks, successful: {successful}")
        
        logger.info(f"MS calculation completed for {successful}/{processed} stocks")
    
    def reload_data(self):
        """Reload semua data ke RAM cache dan pre-calculate MS"""
        logger.info("Reloading data to RAM cache...")
        
        # Clear existing cache
        self.ram_cache.clear()
        self.ms_cache.clear()
        
        # Get available files
        self.files_info = self.get_available_files()
        
        if not self.files_info:
            logger.warning("No data files found")
            return
        
        # Load data dari file ke RAM (ambil 50 file untuk historical data)
        max_files = min(50, len(self.files_info))
        
        for i, file_info in enumerate(self.files_info[:max_files]):
            filename = file_info['filename']
            df = self.load_stock_data(file_info['path'])
            
            if not df.empty:
                # Simpan ke RAM cache dengan key filename
                self.ram_cache[filename] = df
                
            # Log progress setiap 10 file
            if (i + 1) % 10 == 0:
                logger.info(f"Loaded {i + 1}/{max_files} files to cache")
        
        # Pre-calculate semua MS
        self.calculate_all_ms()
        
        self.last_reload = datetime.now()
        logger.info(f"Data reload completed. MS calculated for {len(self.ms_cache)} stocks. Last reload: {self.last_reload}")
    
    def format_value(self, value):
        """Format value dengan B/M/K suffix"""
        if value >= 1_000_000_000:
            return f"{value/1_000_000_000:.1f}B"
        elif value >= 1_000_000:
            return f"{value/1_000_000:.1f}M"
        elif value >= 1_000:
            return f"{value/1_000:.1f}K"
        else:
            return f"{value:.0f}"
    
    def get_filtered_stocks(self):
        """Get SEMUA stocks yang memiliki signal M atau S"""
        results = []
        
        for stock_code, stock_data in self.ms_cache.items():
            if stock_data['signals']:  # Ada minimal 1 signal
                results.append({
                    'kode': stock_code,
                    'close': stock_data['close'],
                    'volume': stock_data['volume'],
                    'value': stock_data['value'],
                    'm': 'M+' if 'M+' in stock_data['signals'] else ('M-' if 'M-' in stock_data['signals'] else '-'),
                    's': next((s for s in stock_data['signals'] if s.startswith('S')), '-')
                })
        
        # Sort by value (highest first)
        results.sort(key=lambda x: x['value'], reverse=True)
        return results
    
    def format_results(self, results, show_all=True):
        """Format results in monospace font - TAMPILKAN SEMUA"""
        if not results:
            return ["*MACD & Stochastic Tracker*\n\nTidak ada saham yang memenuhi kriteria."]
        
        # TAMPILKAN SEMUA RESULTS (tidak ada batasan lagi)
        limited_results = results
        
        # Split ke multiple messages jika terlalu panjang
        messages = []
        current_message = "*MACD & Stochastic Tracker*\n\n"
        current_message += "```\n"
        current_message += f"{'Kode':<6} {'Close':<8} {'M':<4} {'S':<8} {'Val':<8}\n"
        current_message += "-" * 36 + "\n"
        
        lines_in_current_message = 3  # header lines
        max_lines_per_message = 45
        
        for stock in limited_results:
            kode = stock['kode'][:5]
            close = f"{stock['close']:.0f}"
            m = stock['m']
            s = stock['s']
            val = self.format_value(stock['value'])
            
            line = f"{kode:<6} {close:<8} {m:<4} {s:<8} {val:<8}\n"
            
            # Check if adding this line would exceed message limit
            if lines_in_current_message >= max_lines_per_message:
                # Close current message
                current_message += "```"
                messages.append(current_message)
                
                # Start new message
                current_message = "```\n"
                current_message += f"{'Kode':<6} {'Close':<8} {'M':<4} {'S':<8} {'Val':<8}\n"
                current_message += "-" * 36 + "\n"
                lines_in_current_message = 3
            
            current_message += line
            lines_in_current_message += 1
        
        # Close the last message
        current_message += "```"
        
        legend = "\n\n*Legend:*\n"
        legend += "M+ = MACD Golden Cross\n"
        legend += "M- = MACD Death Cross\n"
        legend += "S+ = Stochastic Golden Cross\n"
        legend += "S- = Stochastic Death Cross\n"
        legend += "❤️ = Overbought (>80)\n"
        legend += "💚 = Oversold (<20)\n"
        
        # Tampilkan total semua saham
        current_message += f"\n_Total: {len(results)} saham dengan signal._"
        
        current_message += legend
        messages.append(current_message)
        return messages
    
    def get_cache_info(self):
        """Get info tentang cache yang ada di RAM"""
        ram_usage = sum(df.memory_usage(deep=True).sum() for df in self.ram_cache.values()) / 1024 / 1024
        ms_usage = len(self.ms_cache) * 0.001  # ~1KB per stock MS data
        
        return {
            'files_loaded': len(self.ram_cache),
            'stocks_with_signals': len(self.ms_cache),
            'total_files_available': len(self.files_info),
            'last_reload': self.last_reload,
            'ram_usage_mb': ram_usage,
            'ms_cache_mb': ms_usage,
            'total_memory_mb': ram_usage + ms_usage
        }

# Initialize tracker
ms_tracker = MSTracker()


# Command handlers
@is_authorized_user 
@spy      
@vip       
async def ms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /ms - TAMPILKAN SEMUA"""
    
    try:
        # Check if data sudah di-load
        if not ms_tracker.ram_cache or not ms_tracker.ms_cache:
            await update.message.reply_text(
                "⚠️ Data belum di-load. Silakan gunakan /reload4 terlebih dahulu."
            )
            return
        
        await update.message.reply_text("⏳ Memuat data MACD & Stochastic...")
        
        # Get filtered stocks (SEMUA saham dengan signal)
        results = ms_tracker.get_filtered_stocks()
        
        # Format and send results (SEMUA akan ditampilkan)
        messages = ms_tracker.format_results(results, show_all=True)
        
        for msg in messages:
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in ms_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def reload4_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /reload4"""
    await update.message.reply_text("🔄 Memuat ulang data MACD & Stochastic...")
    
    try:
        ms_tracker.reload_data()
        
        cache_info = ms_tracker.get_cache_info()
        info_text = f"✅ *Data berhasil di-reload!*\n\n"
        info_text += f"📊 Files loaded: {cache_info['files_loaded']}\n"
        info_text += f"📈 Stocks with signals: {cache_info['stocks_with_signals']}\n"
        info_text += f"💾 RAM usage: {cache_info['total_memory_mb']:.1f} MB\n"
        info_text += f"🕐 Last reload: {cache_info['last_reload'].strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in reload4_command: {e}")
        await update.message.reply_text(f"❌ Error reload: {str(e)}")


async def ms_callback(query_data: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk callback button"""
    query = update.callback_query
    await query.answer()
    
    if query_data == "ms_reload":
        await query.message.reply_text("🔄 Memuat ulang data...")
        
        try:
            ms_tracker.reload_data()
            
            cache_info = ms_tracker.get_cache_info()
            info_text = f"✅ *Data berhasil di-reload!*\n\n"
            info_text += f"📊 Files loaded: {cache_info['files_loaded']}\n"
            info_text += f"📈 Stocks with signals: {cache_info['stocks_with_signals']}\n"
            info_text += f"💾 RAM usage: {cache_info['total_memory_mb']:.1f} MB\n"
            info_text += f"🕐 Last reload: {cache_info['last_reload'].strftime('%Y-%m-%d %H:%M:%S')}"
            
            await query.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error in ms_callback reload: {e}")
            await query.message.reply_text(f"❌ Error reload: {str(e)}")
