import json
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import logging
from imporh import*

logger = logging.getLogger(__name__)

class MATracker:
    def __init__(self, cache_dir="/home/ec2-user/database/cache"):
        self.cache_dir = cache_dir
        self.ram_cache = {}  # Cache untuk menyimpan data di RAM
        self.ma_cache = {}   # Cache untuk menyimpan hasil perhitungan MA
        self.files_info = []  # Info file yang tersedia
        self.last_reload = None  # Timestamp reload terakhir
        
        # Load data saat inisialisasi
        self.files_info = self.get_available_files()
        logger.info(f"🚀 MATracker initialized quickly. Found {len(self.files_info)} files. Data will load on first use.")
        
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
            
            # Extract stock codes and closing prices
            kode_saham = data.get('kode_saham', [])
            penutupan = data.get('penutupan', [])
            volume = data.get('volume', [])
            
            # Skip header (index 0) and create dataframe
            stocks = []
            for i in range(1, len(kode_saham)):
                if (i < len(penutupan) and i < len(volume) and 
                    kode_saham[i] and penutupan[i] and volume[i]):
                    try:
                        stocks.append({
                            'kode': str(kode_saham[i]).strip().upper(),
                            'close': float(penutupan[i]),
                            'volume': int(volume[i])
                        })
                    except (ValueError, TypeError):
                        continue
            
            return pd.DataFrame(stocks)
            
        except Exception as e:
            logger.error(f"Error loading stock data from {file_path}: {e}")
            return pd.DataFrame()
    
    def calculate_ma(self, prices, period):
        """Calculate moving average for given period"""
        if len(prices) < period:
            return None
        return np.mean(prices[-period:])
    
    def get_historical_data(self, stock_code, days_needed=250):
        """Get historical closing prices for a stock dari RAM cache"""
        if not self.files_info:
            return []
        
        prices = []
        files_to_check = min(days_needed, len(self.files_info))
        
        for i in range(files_to_check):
            file_info = self.files_info[i]
            filename = file_info['filename']
            
            # Ambil dari RAM cache
            df = self.ram_cache.get(filename, pd.DataFrame())
            if not df.empty:
                stock_row = df[df['kode'] == stock_code.upper()]
                if not stock_row.empty:
                    prices.append(stock_row.iloc[0]['close'])
        
        # Reverse to get chronological order (oldest first)
        return prices[::-1]
    
    def calculate_all_ma(self):
        """Pre-calculate semua MA untuk semua saham"""
        logger.info("Pre-calculating all MA values...")
        
        # Clear existing MA cache
        self.ma_cache.clear()
        
        if not self.files_info or not self.ram_cache:
            return
        
        # Get latest data untuk daftar semua saham
        latest_filename = self.files_info[0]['filename']
        latest_df = self.ram_cache.get(latest_filename, pd.DataFrame())
        
        if latest_df.empty:
            return
        
        ma_periods = [3, 5, 10, 20, 60, 120, 200]  # Added MA3, MA5, MA10
        total_stocks = len(latest_df)
        processed = 0
        successful = 0
        
        for _, row in latest_df.iterrows():
            stock_code = row['kode']
            current_price = row['close']
            volume = row['volume']
            
            # Get historical data
            prices = self.get_historical_data(stock_code, 250)
            
            # Debug log untuk beberapa saham pertama
            if processed < 5:
                logger.info(f"Stock {stock_code}: got {len(prices)} historical prices")
            
            # Lebih fleksibel - minimal MA3 bisa dihitung
            if len(prices) >= 3:  # Changed from 20 to 3 for shorter MAs
                stock_ma = {
                    'kode': stock_code,
                    'close': current_price,
                    'volume': volume,
                    'mas': {}
                }
                
                # Calculate MA yang bisa dihitung
                for period in ma_periods:
                    if len(prices) >= period:  # Cek per periode
                        ma_value = self.calculate_ma(prices, period)
                        if ma_value:
                            stock_ma['mas'][period] = ma_value
                            
                            # Calculate difference percentage
                            diff_pct = ((current_price - ma_value) / ma_value) * 100
                            stock_ma['mas'][f'{period}_diff'] = diff_pct
                
                # Simpan ke MA cache jika ada MA yang berhasil dihitung
                if stock_ma['mas']:
                    self.ma_cache[stock_code] = stock_ma
                    successful += 1
                
            processed += 1
            # Log progress setiap 500 saham
            if processed % 500 == 0:
                logger.info(f"Processed MA for {processed}/{total_stocks} stocks, successful: {successful}")
        
        logger.info(f"MA calculation completed for {successful}/{processed} stocks")
    
    def reload_data(self):
        """Reload semua data ke RAM cache dan pre-calculate MA"""
        logger.info("Reloading data to RAM cache...")
        
        # Clear existing cache
        self.ram_cache.clear()
        self.ma_cache.clear()
        
        # Get available files
        self.files_info = self.get_available_files()
        
        if not self.files_info:
            logger.warning("No data files found")
            return
        
        # Load data dari file ke RAM (ambil max 250 file untuk historical data)
        max_files = min(250, len(self.files_info))
        
        for i, file_info in enumerate(self.files_info[:max_files]):
            filename = file_info['filename']
            df = self.load_stock_data(file_info['path'])
            
            if not df.empty:
                # Simpan ke RAM cache dengan key filename
                self.ram_cache[filename] = df
                
            # Log progress setiap 50 file
            if (i + 1) % 50 == 0:
                logger.info(f"Loaded {i + 1}/{max_files} files to cache")
        
        # Pre-calculate semua MA
        self.calculate_all_ma()
        
        self.last_reload = datetime.now()
        logger.info(f"Data reload completed. MA calculated for {len(self.ma_cache)} stocks. Last reload: {self.last_reload}")
    
    def find_near_ma_stocks(self, ma_period, tolerance=3):
        """Find stocks near MA with tolerance (±3%) dari pre-calculated MA"""
        results = []
        
        for stock_code, stock_data in self.ma_cache.items():
            if ma_period in stock_data['mas']:
                diff_pct = stock_data['mas'].get(f'{ma_period}_diff', 0)
                
                # Check if within tolerance range
                if abs(diff_pct) <= tolerance:
                    results.append({
                        'kode': stock_code,
                        'ma': round(stock_data['mas'][ma_period], 2),
                        'volume': stock_data['volume'],
                        'close': stock_data['close'],
                        'diff_pct': round(diff_pct, 2)
                    })
        
        # Sort by difference percentage (closest to MA first)
        results.sort(key=lambda x: abs(x['diff_pct']))
        return results
    
    def find_cross_ma_stocks(self, ma_period):
        """Find stocks that crossed above MA dari pre-calculated MA"""
        if len(self.files_info) < 2:
            return []
        
        # Load yesterday's data dari RAM cache
        yesterday_filename = self.files_info[1]['filename']
        yesterday_df = self.ram_cache.get(yesterday_filename, pd.DataFrame())
        
        if yesterday_df.empty:
            return []
        
        results = []
        
        for stock_code, stock_data in self.ma_cache.items():
            if ma_period not in stock_data['mas']:
                continue
                
            today_price = stock_data['close']
            ma_value = stock_data['mas'][ma_period]
            
            # Find yesterday's data for same stock
            yesterday_row = yesterday_df[yesterday_df['kode'] == stock_code]
            if yesterday_row.empty:
                continue
                
            yesterday_price = yesterday_row.iloc[0]['close']
            
            # Check cross condition: today > MA and yesterday <= MA
            if today_price > ma_value and yesterday_price <= ma_value:
                results.append({
                    'kode': stock_code,
                    'ma': round(ma_value, 2),
                    'volume': stock_data['volume'],
                    'close': today_price
                })
        
        return results
    
    def find_above_all_ma_stocks(self, tolerance=3):
        """Find stocks above all MA dari pre-calculated MA"""
        results = []
        ma_periods = [3, 5, 10, 20, 60, 120, 200]  # Updated with all MAs
        
        for stock_code, stock_data in self.ma_cache.items():
            current_price = stock_data['close']
            
            # Check if above all MAs
            all_above = True
            mas_values = []
            
            for period in ma_periods:
                if period not in stock_data['mas']:
                    all_above = False
                    break
                
                ma_value = stock_data['mas'][period]
                if current_price <= ma_value:
                    all_above = False
                    break
                    
                mas_values.append(ma_value)
            
            if all_above and mas_values:
                # Find highest MA
                highest_ma = max(mas_values)
                
                # Check if price is within tolerance from highest MA
                diff_pct = ((current_price - highest_ma) / highest_ma) * 100
                
                if diff_pct <= tolerance:
                    results.append({
                        'kode': stock_code,
                        'ma': round(highest_ma, 2),
                        'volume': stock_data['volume'],
                        'close': current_price,
                        'diff_pct': round(diff_pct, 2)
                    })
        
        # Sort by difference percentage (closest to highest MA first)
        results.sort(key=lambda x: x['diff_pct'])
        return results
    
    def find_below_all_ma_stocks(self, tolerance=6):
        """Find stocks below all MA dari pre-calculated MA"""
        results = []
        ma_periods = [20, 60, 120, 200]
     
        for stock_code, stock_data in self.ma_cache.items():
            current_price = stock_data['close']
        
            all_below = True
            mas_values = []
        
            for period in ma_periods:
                if period not in stock_data['mas']:
                    all_below = False
                    break
            
                ma_value = stock_data['mas'][period]
                if current_price >= ma_value:  # harga harus di bawah semua MA
                    all_below = False
                    break
                
                mas_values.append(ma_value)
        
            if all_below and mas_values:
            # Ambil MA terendah
                lowest_ma = min(mas_values)
            
            # Hitung jarak ke MA terendah (negatif = di bawah MA)
                diff_pct = ((current_price - lowest_ma) / lowest_ma) * 100
            
            # Harus di dalam batas toleransi bawah (maks -6%)
                if diff_pct >= -tolerance:
                    results.append({
                        'kode': stock_code,
                        'ma': round(lowest_ma, 2),
                        'volume': stock_data['volume'],
                        'close': current_price,
                        'diff_pct': round(diff_pct, 2)
                    })
    
    # Urutkan dari yang paling dekat ke MA terendah dulu (diff terbesar)
        results.sort(key=lambda x: x['diff_pct'], reverse=True)
        return results

    
    def get_cache_info(self):
        """Get info tentang cache yang ada di RAM"""
        ram_usage = sum(df.memory_usage(deep=True).sum() for df in self.ram_cache.values()) / 1024 / 1024
        
        # Estimasi MA cache size (rough estimate)
        ma_usage = len(self.ma_cache) * 0.001  # ~1KB per stock MA data
        
        return {
            'files_loaded': len(self.ram_cache),
            'stocks_with_ma': len(self.ma_cache),
            'total_files_available': len(self.files_info),
            'last_reload': self.last_reload,
            'ram_usage_mb': ram_usage,
            'ma_cache_mb': ma_usage,
            'total_memory_mb': ram_usage + ma_usage
        }
    
    def format_results(self, results, title, show_all=False):
        """Format results in monospace font"""
        if not results:
            return f"*{title}*\n\nTidak ada saham yang memenuhi kriteria."
        
        # Jika show_all=True, tampilkan semua. Jika tidak, batasi 50
        display_limit = len(results) if show_all else min(50, len(results))
        limited_results = results[:display_limit]
        
        # Split ke multiple messages jika terlalu panjang
        messages = []
        current_message = f"*{title}*\n\n"
        current_message += "```\n"
        current_message += f"{'KODE':<6} {'MA':<8} {'VOLUME':<12} {'CLOSE':<8}\n"
        current_message += "-" * 36 + "\n"
        
        lines_in_current_message = 3  # header lines
        max_lines_per_message = 50
        
        for stock in limited_results:
            kode = stock['kode'][:5]  # Truncate if too long
            ma = f"{stock['ma']:.0f}"
            volume = f"{stock['volume']:,}"
            close = f"{stock['close']:.0f}"
            
            line = f"{kode:<6} {ma:<8} {volume:<12} {close:<8}\n"
            
            # Check if adding this line would exceed message limit
            if lines_in_current_message >= max_lines_per_message:
                # Close current message
                current_message += "```"
                messages.append(current_message)
                
                # Start new message
                current_message = "```\n"
                current_message += f"{'KODE':<6} {'MA':<8} {'VOLUME':<12} {'CLOSE':<8}\n"
                current_message += "-" * 36 + "\n"
                lines_in_current_message = 3
            
            current_message += line
            lines_in_current_message += 1
        
        # Close the last message
        current_message += "```"
        
        if not show_all and len(results) > display_limit:
            current_message += f"\n\n_Menampilkan {display_limit} dari {len(results)} saham._"
        elif show_all:
            current_message += f"\n\n_Total: {len(results)} saham._"
        
        messages.append(current_message)
        return messages

# Initialize tracker
ma_tracker = MATracker()