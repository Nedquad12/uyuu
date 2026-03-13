import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ========================================
# IP TRACKER CACHE DOCUMENTATION
# ========================================
# 
# Import: from ip_tracker import ip_tracker
#
# Akses Cache:
# ------------
# ip_tracker.ip_cache adalah dictionary dengan struktur:
# {
#     'KODE_SAHAM': {
#         'kode': str,        # Kode saham (uppercase)
#         'close': float,     # Harga penutupan terakhir
#         'chg': float,       # Perubahan harga (%) dari hari sebelumnya
#         
#         # MACD Scores (range: -3 to +3 per timeframe)
#         'md': int,          # MACD Daily score
#         'mw': int,          # MACD Weekly score (5 days)
#         'mm': int,          # MACD Monthly score (25 days)
#         
#         # Stochastic Scores (range: -3 to +3 per timeframe)
#         'sd': int,          # Stochastic Daily score
#         'sw': int,          # Stochastic Weekly score (5 days)
#         'sm': int,          # Stochastic Monthly score (25 days)
#         
#         # Indikator Poin per Timeframe
#         'ipd': int,         # IP Daily = md + sd
#         'ipw': int,         # IP Weekly = mw + sw
#         'ipm': int,         # IP Monthly = mm + sm
#         
#         # Indikator Average (Final Score)
#         'ia': float         # IA = (ipd + ipw + ipm) / 3
#     }
# }
#
# Contoh Penggunaan:
# ------------------
# # Get data saham tertentu
# bbca_data = ip_tracker.ip_cache.get('BBCA')
# if bbca_data:
#     print(f"BBCA IA: {bbca_data['ia']}")
#     print(f"Daily IP: {bbca_data['ipd']}")
#
# # Filter saham dengan IA > 3
# high_ia_stocks = [
#     stock for stock in ip_tracker.ip_cache.values()
#     if stock['ia'] > 3.0
# ]
#
# # Sort by IA
# sorted_stocks = sorted(
#     ip_tracker.ip_cache.values(),
#     key=lambda x: x['ia'],
#     reverse=True
# )
#
# # Filter saham bullish semua timeframe
# bullish_all = [
#     stock for stock in ip_tracker.ip_cache.values()
#     if stock['ipd'] > 0 and stock['ipw'] > 0 and stock['ipm'] > 0
# ]
#
# Fungsi Helper yang Tersedia:
# -----------------------------
# ip_tracker.get_stock(kode)          # Get data saham tertentu
# ip_tracker.get_all_stocks()         # Get semua saham sorted by IA
# ip_tracker.reload_data()            # Reload dan recalculate
# ip_tracker.get_cache_info()         # Info memory usage


class IPTracker:
    def __init__(self, cache_dir="/home/ec2-user/database/cache"):
        self.cache_dir = cache_dir
        self.ram_cache = {}  # Cache untuk menyimpan data di RAM
        self.ip_cache = {}   # Cache untuk menyimpan hasil perhitungan IP
        self.files_info = []  # Info file yang tersedia
        self.last_reload = None  # Timestamp reload terakhir
        
        logger.info(f"IPTracker initialized. Use /reload_ip to load data.")
        
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
    
    def calculate_macd(self, prices):
        """Calculate MACD (12, 26, 9)"""
        if len(prices) < 35:  # Need at least 26 + 9 days
            return None, None, None, None
        
        # Calculate EMAs
        series = pd.Series(prices)
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        
        # MACD Line = EMA12 - EMA26
        macd_line = ema12 - ema26
        
        # Signal Line = EMA9 of MACD Line
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        # Current values
        macd_today = macd_line.iloc[-1]
        signal_today = signal_line.iloc[-1]
        
        # Previous values (for cross detection)
        macd_yesterday = macd_line.iloc[-2] if len(macd_line) > 1 else None
        signal_yesterday = signal_line.iloc[-2] if len(signal_line) > 1 else None
        
        return macd_today, signal_today, macd_yesterday, signal_yesterday
    
    def calculate_stochastic(self, highs, lows, closes, k_period=14, d_period=3):
        """Calculate Stochastic Oscillator (%K and %D)"""
        if len(closes) < k_period + d_period:
            return None, None, None, None
        
        # Calculate %K for all periods
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
            else:
                k_values.append(50)  # neutral if no range
        
        if len(k_values) < d_period:
            return None, None, None, None
        
        # Current %K and %D
        k_today = k_values[-1]
        d_today = np.mean(k_values[-d_period:])
        
        # Previous %K and %D (for cross detection)
        k_yesterday = k_values[-2] if len(k_values) > 1 else None
        d_yesterday = np.mean(k_values[-d_period-1:-1]) if len(k_values) > d_period else None
        
        return k_today, d_today, k_yesterday, d_yesterday
    
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
    
    def aggregate_to_weekly(self, closes, highs, lows, period=5):
        """Aggregate daily data to weekly (5 days)"""
        if len(closes) < period:
            return [], [], []
        
        weekly_closes = []
        weekly_highs = []
        weekly_lows = []
        
        for i in range(0, len(closes), period):
            window_closes = closes[i:i+period]
            window_highs = highs[i:i+period]
            window_lows = lows[i:i+period]
            
            if window_closes:
                weekly_closes.append(window_closes[-1])  # Last close of the period
                weekly_highs.append(max(window_highs))
                weekly_lows.append(min(window_lows))
        
        return weekly_closes, weekly_highs, weekly_lows
    
    def aggregate_to_monthly(self, closes, highs, lows, period=25):
        """Aggregate daily data to monthly (25 days)"""
        if len(closes) < period:
            return [], [], []
        
        monthly_closes = []
        monthly_highs = []
        monthly_lows = []
        
        for i in range(0, len(closes), period):
            window_closes = closes[i:i+period]
            window_highs = highs[i:i+period]
            window_lows = lows[i:i+period]
            
            if window_closes:
                monthly_closes.append(window_closes[-1])  # Last close of the period
                monthly_highs.append(max(window_highs))
                monthly_lows.append(min(window_lows))
        
        return monthly_closes, monthly_highs, monthly_lows
    
    def calculate_macd_score(self, macd_today, signal_today, macd_yesterday, signal_yesterday):
        """Calculate MACD score based on conditions"""
        score = 0
        
        if macd_today is None or signal_today is None:
            return 0
        
        # Condition 1: MACD positive/negative
        if macd_today > 0:
            score += 1
        elif macd_today < 0:
            score -= 1
        
        # Condition 2: Golden Cross / Death Cross
        if macd_yesterday is not None and signal_yesterday is not None:
            # Golden Cross: MACD crosses above Signal
            if macd_today > signal_today and macd_yesterday <= signal_yesterday:
                score += 1
            # Death Cross: MACD crosses below Signal
            elif macd_today < signal_today and macd_yesterday >= signal_yesterday:
                score -= 1
        
        # Condition 3: MACD above/below Signal
        if macd_today > signal_today:
            score += 1
        elif macd_today < signal_today:
            score -= 1
        
        return score
    
    def calculate_stoch_score(self, k_today, d_today, k_yesterday, d_yesterday):
        """Calculate Stochastic score based on conditions"""
        score = 0
        
        if k_today is None or d_today is None:
            return 0
        
        # Condition 1: Oversold/Overbought
        if k_today < 25:
            score += 1
        elif k_today > 85:
            score -= 1
        
        # Condition 2: Golden Cross / Death Cross
        if k_yesterday is not None and d_yesterday is not None:
            # Golden Cross: K crosses above D
            if k_today > d_today and k_yesterday <= d_yesterday:
                score += 1
            # Death Cross: K crosses below D
            elif k_today < d_today and k_yesterday >= d_yesterday:
                score -= 1
        
        # Condition 3: K above/below D
        if k_today > d_today:
            score += 1
        elif k_today < d_today:
            score -= 1
        
        return score
    
    def calculate_ip_for_stock(self, stock_code):
        """Calculate IP (Indikator Poin) for a stock across all timeframes"""
        # Get historical data (50 days for daily, need more for weekly/monthly)
        closes, highs, lows = self.get_historical_data(stock_code, 50)
        
        if len(closes) < 35:  # Minimum for MACD
            return None
        
        # === DAILY ===
        macd_d, signal_d, macd_d_prev, signal_d_prev = self.calculate_macd(closes)
        k_d, d_d, k_d_prev, d_d_prev = self.calculate_stochastic(highs, lows, closes)
        
        md = self.calculate_macd_score(macd_d, signal_d, macd_d_prev, signal_d_prev)
        sd = self.calculate_stoch_score(k_d, d_d, k_d_prev, d_d_prev)
        ipd = md + sd
        
        # === WEEKLY (5 days) ===
        weekly_closes, weekly_highs, weekly_lows = self.aggregate_to_weekly(closes, highs, lows, 5)
        
        if len(weekly_closes) >= 35:
            macd_w, signal_w, macd_w_prev, signal_w_prev = self.calculate_macd(weekly_closes)
            k_w, d_w, k_w_prev, d_w_prev = self.calculate_stochastic(weekly_highs, weekly_lows, weekly_closes)
            
            mw = self.calculate_macd_score(macd_w, signal_w, macd_w_prev, signal_w_prev)
            sw = self.calculate_stoch_score(k_w, d_w, k_w_prev, d_w_prev)
            ipw = mw + sw
        else:
            mw = 0
            sw = 0
            ipw = 0
        
        # === MONTHLY (25 days) ===
        monthly_closes, monthly_highs, monthly_lows = self.aggregate_to_monthly(closes, highs, lows, 25)
        
        if len(monthly_closes) >= 35:
            macd_m, signal_m, macd_m_prev, signal_m_prev = self.calculate_macd(monthly_closes)
            k_m, d_m, k_m_prev, d_m_prev = self.calculate_stochastic(monthly_highs, monthly_lows, monthly_closes)
            
            mm = self.calculate_macd_score(macd_m, signal_m, macd_m_prev, signal_m_prev)
            sm = self.calculate_stoch_score(k_m, d_m, k_m_prev, d_m_prev)
            ipm = mm + sm
        else:
            mm = 0
            sm = 0
            ipm = 0
        
        # === INDIKATOR AVERAGE ===
        ia = (ipd + ipw + ipm) / 3.0
        
        # Get current price for change calculation
        current_price = closes[-1]
        previous_price = closes[-2] if len(closes) > 1 else current_price
        chg = ((current_price - previous_price) / previous_price * 100) if previous_price != 0 else 0
        
        return {
            'kode': stock_code,
            'close': current_price,
            'chg': chg,
            
            # MACD scores per timeframe
            'md': md,
            'mw': mw,
            'mm': mm,
            
            # Stochastic scores per timeframe
            'sd': sd,
            'sw': sw,
            'sm': sm,
            
            # IP per timeframe
            'ipd': ipd,
            'ipw': ipw,
            'ipm': ipm,
            
            # Indikator Average
            'ia': ia
        }
    
    def calculate_all_ip(self):
        """Pre-calculate semua IP untuk semua saham"""
        logger.info("Pre-calculating all IP values...")
        
        # Clear existing IP cache
        self.ip_cache.clear()
        
        if not self.files_info or not self.ram_cache:
            return
        
        # Get latest data untuk daftar semua saham
        latest_filename = self.files_info[0]['filename']
        latest_df = self.ram_cache.get(latest_filename, pd.DataFrame())
        
        if latest_df.empty:
            return
        
        total_stocks = len(latest_df)
        processed = 0
        successful = 0
        
        for _, row in latest_df.iterrows():
            stock_code = row['kode']
            
            # Calculate IP for this stock
            ip_data = self.calculate_ip_for_stock(stock_code)
            
            if ip_data:
                self.ip_cache[stock_code] = ip_data
                successful += 1
            
            processed += 1
            
            # Log progress setiap 500 saham
            if processed % 500 == 0:
                logger.info(f"Processed IP for {processed}/{total_stocks} stocks, successful: {successful}")
        
        logger.info(f"IP calculation completed for {successful}/{processed} stocks")
    
    def reload_data(self):
        """Reload semua data ke RAM cache dan pre-calculate IP"""
        logger.info("Reloading data to RAM cache...")
        
        # Clear existing cache
        self.ram_cache.clear()
        self.ip_cache.clear()
        
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
        
        # Pre-calculate semua IP
        self.calculate_all_ip()
        
        self.last_reload = datetime.now()
        logger.info(f"Data reload completed. IP calculated for {len(self.ip_cache)} stocks. Last reload: {self.last_reload}")
    
    def get_all_stocks(self):
        """Get ALL stocks sorted by IA (descending)"""
        results = list(self.ip_cache.values())
        
        # Sort by IA (highest first)
        results.sort(key=lambda x: x['ia'], reverse=True)
        
        return results
    
    def get_stock(self, stock_code):
        """Get specific stock by code"""
        return self.ip_cache.get(stock_code.upper())
    
    def format_results(self, results):
        """Format results in monospace font"""
        if not results:
            return ["*Indikator Poin (IP)*\n\nTidak ada data saham."]
        
        messages = []
        current_message = "*Indikator Poin (IP)*\n\n"
        current_message += "```\n"
        current_message += f"{'Kode':<6} {'Chg':<7} {'M':<4} {'S':<4} {'IPd':<4} {'IPw':<4} {'IPm':<4} {'IA':<6}\n"
        current_message += "-" * 48 + "\n"
        
        lines_in_current_message = 3  # header lines
        max_lines_per_message = 45
        
        for stock in results:
            kode = stock['kode'][:5]
            chg = f"{stock['chg']:+.1f}%"
            m = f"{stock['md']:+d}"  # M = Daily MACD
            s = f"{stock['sd']:+d}"  # S = Daily Stochastic
            ipd = f"{stock['ipd']:+d}"
            ipw = f"{stock['ipw']:+d}"
            ipm = f"{stock['ipm']:+d}"
            ia = f"{stock['ia']:.1f}"
            
            line = f"{kode:<6} {chg:<7} {m:<4} {s:<4} {ipd:<4} {ipw:<4} {ipm:<4} {ia:<6}\n"
            
            # Check if adding this line would exceed message limit
            if lines_in_current_message >= max_lines_per_message:
                # Close current message
                current_message += "```"
                messages.append(current_message)
                
                # Start new message
                current_message = "```\n"
                current_message += f"{'Kode':<6} {'Chg':<7} {'M':<4} {'S':<4} {'IPd':<4} {'IPw':<4} {'IPm':<4} {'IA':<6}\n"
                current_message += "-" * 48 + "\n"
                lines_in_current_message = 3
            
            current_message += line
            lines_in_current_message += 1
        
        # Close the last message
        current_message += "```"
        current_message += f"\n\n_Total: {len(results)} saham_"
        current_message += "\n\n*Legend:*\n"
        current_message += "M/S = MACD/Stochastic Daily score\n"
        current_message += "IPd = IP Daily\n"
        current_message += "IPw = IP Weekly (5 days)\n"
        current_message += "IPm = IP Monthly (25 days)\n"
        current_message += "IA = (IPd + IPw + IPm) / 3"
        
        messages.append(current_message)
        return messages
    
    def format_single_stock(self, stock_data):
        """Format single stock result with detailed breakdown"""
        if not stock_data:
            return "Data saham tidak ditemukan."
        
        message = f"*{stock_data['kode']} - Detail IP*\n\n"
        message += "```\n"
        message += f"Close      : {stock_data['close']:.0f}\n"
        message += f"Change     : {stock_data['chg']:+.2f}%\n"
        message += "\n"
        message += "Daily:\n"
        message += f"  MACD     : {stock_data['md']:+d}\n"
        message += f"  Stoch    : {stock_data['sd']:+d}\n"
        message += f"  IP Daily : {stock_data['ipd']:+d}\n"
        message += "\n"
        message += "Weekly (5d):\n"
        message += f"  MACD     : {stock_data['mw']:+d}\n"
        message += f"  Stoch    : {stock_data['sw']:+d}\n"
        message += f"  IP Weekly: {stock_data['ipw']:+d}\n"
        message += "\n"
        message += "Monthly (25d):\n"
        message += f"  MACD     : {stock_data['mm']:+d}\n"
        message += f"  Stoch    : {stock_data['sm']:+d}\n"
        message += f"  IP Month : {stock_data['ipm']:+d}\n"
        message += "\n"
        message += f"IA Average : {stock_data['ia']:.2f}\n"
        message += "```"
        
        return message
    
    def get_cache_info(self):
        """Get info tentang cache yang ada di RAM"""
        ram_usage = sum(df.memory_usage(deep=True).sum() for df in self.ram_cache.values()) / 1024 / 1024
        ip_usage = len(self.ip_cache) * 0.001  # ~1KB per stock IP data
        
        return {
            'files_loaded': len(self.ram_cache),
            'stocks_with_ip': len(self.ip_cache),
            'total_files_available': len(self.files_info),
            'last_reload': self.last_reload,
            'ram_usage_mb': ram_usage,
            'ip_cache_mb': ip_usage,
            'total_memory_mb': ram_usage + ip_usage
        }


# Initialize tracker (singleton)
ip_tracker = IPTracker()