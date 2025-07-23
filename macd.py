import yfinance as yf
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.pyplot as plt
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram import Update
import io
import os
import random
from datetime import datetime
import pytz
import asyncio
from datetime import datetime, timedelta
from telegram.ext import MessageHandler, filters
import time
from collections import defaultdict
import gc
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import pytz
from collections import deque

request_queue = deque()

user_screener_results = defaultdict(list)
user_screener_page = defaultdict(int)

# === Flag user busy untuk mencegah paralel ===
user_busy_flags = defaultdict(bool)

# Token bot Telegram (ganti dengan token bot Anda)
BOT_TOKEN = "7654841822:AAEmjomyCfpyGjvZeAikRXZmZn68KvCYR9g"

WHITELIST_USER_IDS = [
    6208519947, 5751902978
]

user_last_request = defaultdict(float)
REQUEST_COOLDOWN = 3  # 3 detik delay

class TradingIndicator:
    
    def __init__(self):
        pass
    
    def calculate_macd(self, data, fast=12, slow=26, signal=9):
        """Menghitung MACD"""
        ema_fast = data['Close'].ewm(span=fast).mean()
        ema_slow = data['Close'].ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def calculate_stochastic(self, data, k_period=14, d_period=3):
        """Menghitung Stochastic %K dan %D"""
        low_min = data['Low'].rolling(window=k_period).min()
        high_max = data['High'].rolling(window=k_period).max()
        
        k_percent = ((data['Close'] - low_min) / (high_max - low_min)) * 100
        d_percent = k_percent.rolling(window=d_period).mean()
        
        return k_percent, d_percent
    
    def calculate_m_value_combined(self, data, macd_line, signal_line, period=14, atr_multiplier=1.1):
        """Menghitung nilai M (MACD combined) dengan threshold gabungan ATR + Std Dev"""
        # Hitung ATR
        high_low = data['High'] - data['Low']
        high_close = (data['High'] - data['Close'].shift()).abs()
        low_close = (data['Low'] - data['Close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        # Threshold hanya dari ATR
        m_combined = macd_line + signal_line
        threshold = (atr * atr_multiplier)
        threshold = np.maximum(threshold, 0.05)  # floor 0.05
        threshold = threshold.fillna(0.01)  # hindari division by zero

        m_values = []
        for val, th in zip(m_combined, threshold):
            if pd.isna(val) or pd.isna(th):
                m_values.append(0)
            elif val > th:
                m_values.append(1)  # bullish
            elif val < -th:
                m_values.append(-1)  # bearish
            else:
                m_values.append(0)  # netral

        return pd.Series(m_values, index=m_combined.index)
    
    def calculate_s_value(self, k_percent, d_percent, macd_line):
        """Menghitung nilai S (Stochastic combined) dengan logika oversold & overbought pintar"""
        s_combined = k_percent + d_percent
        s_values = []

        oversold_days = 0
        overbought_days = 0

        for i, val in enumerate(s_combined):  # ← Perbaiki: gunakan enumerate untuk mendapatkan index
            if pd.isna(val):
                s_values.append(0)
                oversold_days = 0
                overbought_days = 0
            elif 0 <= val <= 25:
                oversold_days += 1
                overbought_days = 0
                if oversold_days == 1:
                    s_values.append(-1)
                elif oversold_days == 2:
                    s_values.append(0)
                elif oversold_days >= 3:
                    if i < len(macd_line) and macd_line.iloc[i] > 0:  # ← Perbaiki: cek bounds
                        s_values.append(1)
                    else:
                        s_values.append(0)
            elif val >= 75:
                overbought_days += 1
                oversold_days = 0
                if overbought_days == 1:
                    s_values.append(1)
                elif overbought_days == 2:
                    s_values.append(0)
                else:
                    s_values.append(-1)
            else:
                s_values.append(1)
                oversold_days = 0
                overbought_days = 0

        return pd.Series(s_values, index=s_combined.index)

    
    def calculate_price_changes(self, data, atr_period=14, atr_multiplier=1.5, point_boost=1.2):
        """Menghitung perubahan harga 1, 2, 3 hari dengan ATR-aware"""
        close_prices = data['Close']
    
    # Hitung ATR
        high_low = data['High'] - data['Low']
        high_close = (data['High'] - data['Close'].shift()).abs()
        low_close = (data['Low'] - data['Close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=atr_period).mean()
        atr = atr.clip(lower=0.05)
    
        ku1, ku2, ku3 = [], [], []
        kd1, kd2, kd3 = [], [], []
    
        for i in range(len(close_prices)):
            atr_val = atr.iloc[i] if not pd.isna(atr.iloc[i]) else 0

        # ===== 1 hari =====
            if i >= 1:
                change = close_prices.iloc[i] - close_prices.iloc[i-1]
                abs_change = abs(change)

                multiplier = 1.0 + min(abs_change / (atr_val * atr_multiplier), 1.0)

                if change > 0:
                    ku1.append(0.4 * multiplier)
                    kd1.append(-0.4 * multiplier)
                elif change < 0:
                    ku1.append(-0.4 * multiplier)
                    kd1.append(0.4 * multiplier)
                else:
                    ku1.append(0)
                    kd1.append(0)
            else:
                ku1.append(0)
                kd1.append(0)
        
        # ===== 2 hari =====
            if i >= 2:
                change = close_prices.iloc[i] - close_prices.iloc[i-2]
                abs_change = abs(change)
  
                multiplier = point_boost if abs_change > (atr_val * atr_multiplier) else 1.0

                if change > 0:
                        ku2.append(0.3 * multiplier)
                        kd2.append(-0.3 * multiplier)
                elif change < 0:
                        ku2.append(-0.3 * multiplier)
                        kd2.append(0.3 * multiplier)
                else:
                        ku2.append(0)
                        kd2.append(0)
            else:
                 ku2.append(0)
                 kd2.append(0)
        
        # ===== 3 hari =====
            if i >= 3:
                change = close_prices.iloc[i] - close_prices.iloc[i-3]
                abs_change = abs(change)

                multiplier = point_boost if abs_change > (atr_val * atr_multiplier) else 1.0

                if change > 0:
                    ku3.append(0.3 * multiplier)
                    kd3.append(-0.3 * multiplier)
                elif change < 0:
                     ku3.append(-0.3 * multiplier)
                     kd3.append(0.3 * multiplier)
                else:
                     ku3.append(0)
                     kd3.append(0)
            else:
                 ku3.append(0)
                 kd3.append(0)
        
        return (pd.Series(ku1, index=close_prices.index),
                pd.Series(ku2, index=close_prices.index),
                pd.Series(ku3, index=close_prices.index),
                pd.Series(kd1, index=close_prices.index),
                pd.Series(kd2, index=close_prices.index),
                pd.Series(kd3, index=close_prices.index))
    
    def calculate_signal_changes(self, macd_line, signal_line, k_percent, d_percent, data, period=14, atr_multiplier=1.2, std_multiplier=1.2):
        """Menghitung perubahan sinyal MACD dan Stochastic"""
        mup = []
        mdn = []
        # Hitung ATR
        high_low = data['High'] - data['Low']
        high_close = (data['High'] - data['Close'].shift()).abs()
        low_close = (data['Low'] - data['Close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

    # Hitung StdDev dari signal_line
        rolling_std = signal_line.rolling(window=period).std()

        threshold = (atr * atr_multiplier) + (rolling_std * std_multiplier)
        threshold = threshold.fillna(0.01)

        for i in range(len(signal_line)):
            if i >= 1:
                change = signal_line.iloc[i] - signal_line.iloc[i-1]
                macd_val = macd_line.iloc[i]

                if abs(change) > threshold.iloc[i]:  # Gunakan threshold dinamis
                    if change > 0:
                        mup.append(1)
                        mdn.append(0)
                    elif change < 0:
                        mup.append(0)
                        mdn.append(-1)
                else:  # Perubahan kecil, netral
                    mup.append(0)
                    mdn.append(0)
            else:
                mup.append(0)
                mdn.append(0)
        
        # sup - sinyal Stochastic naik
        sup = []
        sdn = []

        overbought_days = 0
        oversold_days = 0

        stoch_combined = k_percent + d_percent

        for i in range(len(k_percent)):
            if pd.isna(stoch_combined.iloc[i]):
                sup.append(0)
                sdn.append(0)
                overbought_days = 0
                oversold_days = 0
                continue

            val = stoch_combined.iloc[i]

         # Normal area
            if 25 < val < 75:
                sup.append(0.5)
                sdn.append(-0.5)
                overbought_days = 0
                oversold_days = 0
        # Oversold area
            elif 0 <= val <= 25:
                oversold_days += 1
                overbought_days = 0
                if oversold_days == 1:
                    sup.append(0)
                    sdn.append(-1)
                elif oversold_days == 2:
                   sup.append(0)
                   sdn.append(0)
                elif oversold_days >= 3:
                    if i < len(macd_line) and macd_line.iloc[i] > 0:  # ← Perbaiki: cek bounds
                        sup.append(1)
                        sdn.append(0)
                    else:
                        sup.append(0)
                        sdn.append(0)

        # Overbought area (75–100)
            elif 75 <= val < 90:
                overbought_days += 1
                oversold_days = 0
                if overbought_days <= 2:
                    sup.append(0.5)  # Hari pertama & kedua overbought
                    sdn.append(0)
                else:
                   sup.append(0) # Hari ketiga overbought
                   sdn.append(-1)

            elif val >= 90:
                overbought_days += 1
                oversold_days = 0
                if overbought_days == 1:
                    sup.append(0)  # Hari pertama >90
                    sdn.append(-1)
                else:
                    sup.append(0)  # Hari kedua >90
                    sdn.append(-1.5 if macd_line.iloc[i] < 0 else 0)
            else:
                sup.append(0)
                sdn.append(0)

        
        return (pd.Series(mup, index=signal_line.index),
                pd.Series(mdn, index=signal_line.index),
                pd.Series(sup, index=k_percent.index),
                pd.Series(sdn, index=k_percent.index))
    
    def calculate_combined_trend(self, m_values, s_values, weight_ratio = 1.1):
        """Menghitung trend gabungan m dan s"""
        m_gt_s = []
        m_lt_s = []
        msdn = []
        msdu = [] 
        
        for i in range(len(m_values)):
            if i >= 1:
                m_curr, m_prev = m_values.iloc[i], m_values.iloc[i-1]
                s_curr, s_prev = s_values.iloc[i], s_values.iloc[i-1]
                
                # (m>s) comparison
                if m_curr > s_curr * weight_ratio:
                    m_gt_s.append(1)
                    m_lt_s.append(0)
                elif m_curr < s_curr * weight_ratio:
                    m_gt_s.append(0)
                    m_lt_s.append(-1)
                else:
                    m_gt_s.append(0)
                    m_lt_s.append(0)
                
                # msdn - penurunan bersama
                m_trend = m_curr - m_prev
                s_trend = s_curr - s_prev
                
                if m_trend < 0 and s_trend < 0:  # Turun bersamaan
                  msdn.append(1)
                  msdu.append(0)
                elif m_trend > 0 and s_trend > 0:  # Naik bersamaan
                  msdn.append(0)
                  msdu.append(1)
                else: # Tidak bersamaan
                  msdn.append(0)
                  msdu.append(0)

            else:
                m_gt_s.append(0)
                m_lt_s.append(0)
                msdn.append(0)
                msdu.append(0) 
        
        return (pd.Series(m_gt_s, index=m_values.index),
                pd.Series(m_lt_s, index=m_values.index),
                pd.Series(msdn, index=m_values.index),
                pd.Series(msdu, index=m_values.index))
        
    def calculate_moving_averages(self, data, timeframe):
        """Menghitung Moving Averages"""
        if timeframe == 'Daily':
           ma5 = data['Close'].rolling(window=5).mean()
           ma20 = data['Close'].rolling(window=20).mean()
           ma60 = data['Close'].rolling(window=60).mean()
           ma90 = data['Close'].rolling(window=90).mean()
           ma120 = data['Close'].rolling(window=120).mean()
    
           return ma5, ma20, ma60, ma90, ma120
    
        elif timeframe == 'Weekly':
           ma3 = data['Close'].rolling(window=3).mean()
           ma5 = data['Close'].rolling(window=5).mean()
           ma20 = data['Close'].rolling(window=20).mean()
           return ma3, ma5, ma20
    
        elif timeframe == 'Monthly':
            ma3 = data['Close'].rolling(window=3).mean()
            ma5 = data['Close'].rolling(window=5).mean()
            return ma3, ma5
    
    def format_ma_caption(self, current_price, mas, rsi_value, timeframe, atl_value, ath_value):
        """Format caption untuk MA dan RSI"""
        def format_ma_value(ma_value):
            if pd.isna(ma_value):
                return "N/A"
            diff = ((ma_value - current_price) / ma_value) * 100
            sign = "+" if diff >= 0 else ""
            return f"{ma_value:.2f} ({sign}{diff:.2f}%)"

        caption = f"Price (Close): {current_price:.2f}\n"
        caption += f"RK: {ath_value:.2f}\n"
        caption += f"SK: {atl_value:.2f}\n"
        caption += f"RSI: {rsi_value:.2f}\n"
    
        if timeframe == 'Daily':
           caption += f"MA5: {format_ma_value(mas[0])}\n"
           caption += f"MA20: {format_ma_value(mas[1])}\n"
           caption += f"MA60: {format_ma_value(mas[2])}\n"
           caption += f"MA90: {format_ma_value(mas[3])}\n"
           caption += f"MA120: {format_ma_value(mas[4])}"
             
        elif timeframe == 'Weekly':
           caption += f"MA3: {format_ma_value(mas[0])}\n"
           caption += f"MA5: {format_ma_value(mas[1])}\n"
           caption += f"MA20: {format_ma_value(mas[2])}"
    
        elif timeframe == 'Monthly':
           caption += f"MA3: {format_ma_value(mas[0])}\n"
           caption += f"MA5: {format_ma_value(mas[1])}"

        return caption
    
    def calculate_rsi(self, data, period=14):
       """Menghitung RSI"""
       delta = data['Close'].diff()
       gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
       loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
       rs = gain / loss
       rsi = 100 - (100 / (1 + rs))
       return rsi
    
    def calculate_final_formula(self, data, timeframe):
        """Menghitung rumus final"""
        # Hitung indikator
        macd_line, signal_line, histogram = self.calculate_macd(data)
        k_percent, d_percent = self.calculate_stochastic(data)
        
        # Hitung nilai M dan S
        m_values = self.calculate_m_value_combined(data, macd_line, signal_line, period=14, atr_multiplier=1.1)
        s_values = self.calculate_s_value(k_percent, d_percent, macd_line)
        rsi = self.calculate_rsi(data)
        
        # Hitung perubahan harga
        ku1, ku2, ku3, kd1, kd2, kd3 = self.calculate_price_changes(data, atr_period=14, atr_multiplier=1.5, point_boost=1.3)
        
        # Hitung perubahan sinyal
        mup, mdn, sup, sdn = self.calculate_signal_changes(macd_line, signal_line, k_percent, d_percent, data, period =14, atr_multiplier=1.2, std_multiplier=1.2)
        
        # Hitung trend gabungan
        m_gt_s, m_lt_s, msdn , msdu= self.calculate_combined_trend(m_values, s_values, weight_ratio = 1.1)
        
        # Rumus final: (m>s)+mup+sup+ku1+ku2+2*ku3-kd1-kd2-2*kd3-mdn-sdn-(m<s)-msdn
        final_score = (m_gt_s + mup*1.25 + sup + ku1 + ku2 + ku3 + msdu - 
                      kd1 - kd2 - kd3 - mdn*1.25 - sdn - m_lt_s - msdn) 
        
        mas = self.calculate_moving_averages(data, timeframe)
        
        return final_score, {
            'macd_line': macd_line,
            'signal_line': signal_line,
            'histogram': histogram,
            'k_percent': k_percent,
            'd_percent': d_percent,
            'm_values': m_values,
            's_values': s_values,
            'mas' : mas,
            'rsi' : rsi
        }
        
    def create_chart(self, data, final_score, indicators, timeframe, symbol):
        """Membuat chart dengan mplfinance"""
    
        # Siapkan data untuk mplfinance
        # Data harus memiliki kolom OHLC dengan nama yang tepat
        chart_data = data.copy()
        
        # Hitung MA5 dari final_score
        ma5_final_score = final_score.rolling(window=5).mean()

    
        # Buat additional plots untuk final score
        ap_dict = [
            mpf.make_addplot(final_score, panel=1, color='red', width=2, 
                            ylabel='FS', type='line'),
        ]
        
        ap_dict.append(
            mpf.make_addplot(ma5_final_score, panel=1, color='blue', linestyle='--', width=1.5, label='MA5 F')
        )
 
            # Tambahkan garis referensi (0,5,2,-2,-5)
        ref_lines = [0, 5, 2, -2, -5]
        ref_colors = ['black', 'green', 'lightgreen', 'orange', 'red']
        ref_styles = ['-', '--', '--', '--', '--']

        for line, color, style in zip(ref_lines, ref_colors, ref_styles):
           ap_dict.append(mpf.make_addplot([line] * len(final_score), 
                                         panel=1, color=color, 
                                        linestyle=style, alpha=0.7))
           
    # Tambahkan garis referensi untuk final score
        if len(final_score) > 0:
            ref_lines = [0, 5, 2, -2, -5]
            ref_colors = ['black', 'green', 'lightgreen', 'orange', 'red']
            ref_styles = ['-', '--', '--', '--', '--']
        
            for line, color, style in zip(ref_lines, ref_colors, ref_styles):
                ap_dict.append(mpf.make_addplot([line] * len(final_score), 
                                              panel=1, color=color, 
                                              linestyle=style, alpha=0.7))
    
    # Buat style custom
        mc = mpf.make_marketcolors(up='g', down='r', 
                                  edge='inherit',
                                  wick={'up':'green', 'down':'red'},
                                  volume='in')
    
        s = mpf.make_mpf_style(marketcolors=mc, 
                      gridstyle='-', 
                      gridcolor='lightgray')
    
    # Buat chart
        fig, axes = mpf.plot(chart_data,
                       type='candle',
                       style=s,
                       title=f'{symbol.replace(".JK", "")} - {timeframe} Trading Analysis',
                       ylabel='Price',
                       addplot=ap_dict,
                       returnfig=True,
                       figsize=(12, 10),
                       tight_layout=True)
    
    # Simpan ke buffer
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=120, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)
        plt.close('all')    # Pastikan semua figure ditutup
        gc.collect()    
     
        return buffer

# Inisialisasi calculator
calculator = TradingIndicator()

def is_authorized_user(update: Update) -> bool:
    """Check if user is authorized to use bot in DM"""
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    
    # Allow in groups and channels
    if chat_type in ['group', 'supergroup', 'channel']:
        return True
    
    # Check whitelist for private chats
    if chat_type == 'private':
        return user_id in WHITELIST_USER_IDS
    
    return False

async def cmd_calculate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /c"""
    if not is_authorized_user(update):
        await update.message.reply_text(
            "Hi!! Maaf kamu tidak terdaftar sebagai member premium." "Jika ingin  bergabung menjadi member premium dan menggunakan bot sesuka hati bisa hubungi @Rendanggedang"
        )
        return
    try:
        # Parse argumen
        if not context.args:
            await update.message.reply_text("Gunakan: /c SYMBOL\nContoh: /c BBCA")
            return
        
        user_id = update.effective_user.id
        current_time = time.time()
        last_request_time = user_last_request[user_id]
    
        time_since_last = current_time - last_request_time
    
        if time_since_last < REQUEST_COOLDOWN:
            remaining_time = REQUEST_COOLDOWN - time_since_last
            await update.message.reply_text(
                f"⏳ Mohon tunggu {remaining_time:.1f} detik sebelum request berikutnya."
            )
            return
        
        request_queue.append(user_id)
        queue_position = list(request_queue).index(user_id) + 1

        if queue_position > 1:
           await update.message.reply_text(
               f"⏳ Anda berada di antrian ke [{queue_position}] harap bersabar..."
           )
        
        symbol = context.args[0].upper()

     # Auto-add .JK for Indonesian stocks if not already present
        if not ('.' in symbol or symbol.endswith('.JK')):
           symbol += '.JK'
        
        # Kirim pesan loading
        loading_msg = await update.message.reply_text(f"📊 Menganalisis {symbol.replace('.JK', '')}...")
        
        # Timeframe dan periode
        timeframes = {
            'Daily': {'period': '1d', 'days': 40, 'download_days' : 250},
            'Weekly': {'period': '1wk', 'days': 10*7, 'download_days' : 25*7},  # 40 minggu
            'Monthly': {'period': '1mo', 'days': 10*30, 'download_days' : 15*30}  # 60 bulan
        }
        
        charts = []
        timeframe_scores = {}
       
        for tf_name, tf_config in timeframes.items():
            print(f"🔍 Processing {tf_name}...")  # Debug log
            try:
                # Download data
                end_date = datetime.now()
                
                if tf_name == 'Daily':
                    download_days = 250
                    display_days = 40
                elif tf_name == 'Weekly':
                    download_days = 25*7
                    display_days = 10*7
                else:  # Monthly
                    download_days = 15*30
                    display_days = 10*30
                
                start_date = end_date - timedelta(days=download_days)
                
                print(f"📊 Downloading {tf_name} data for {symbol}...")  # Debug log
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date, end=end_date, interval=tf_config['period'])
                # Update candle terakhir pakai harga live (hanya untuk Close)
                try:
                    live_data = ticker.history(period="1d", interval="1m")
                    if not live_data.empty:
                        live_close = live_data['Close'].iloc[-1]
                        data.iloc[-1, data.columns.get_loc('Close')] = live_close
                except Exception:
                   pass
 
                if data.empty:
                   print(f"❌ No data for {tf_name}")  # Debug log
                   continue
                
                print(f"✅ Data downloaded: {len(data)} rows for {tf_name}")  # Debug log
                
                # Hitung indikator
                print(f"🔢 Calculating indicators for {tf_name}...")  # Debug log
                final_score, indicators = calculator.calculate_final_formula(data, tf_name)
                print(f"✅ Indicators calculated for {tf_name}")  # Debug log
                
                # Potong data untuk display
                display_data = data.tail(display_days) if len(data) > display_days else data
                display_score = final_score.tail(display_days) if len(final_score) > display_days else final_score
                
                # Pastikan panjang sama
                min_length = min(len(display_data), len(display_score))
                display_data = display_data.tail(min_length)
                display_score = display_score.tail(min_length)
                
                print(f"📈 Creating chart for {tf_name}...")  # Debug log
                # Buat chart
                chart_buffer = calculator.create_chart(display_data, display_score, indicators, tf_name, symbol)
                current_price = data['Close'].iloc[-1]
                
                atl_value = data['Close'].min()
                ath_value = data['Close'].max()
                # Hitung ATR (volatilitas) untuk membuat Support & Resist dinamis
                high_low = data['High'] - data['Low']
                high_close = (data['High'] - data['Close'].shift()).abs()
                low_close = (data['Low'] - data['Close'].shift()).abs()
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean()

                multiplier = 1.07  # ATR multiplier sesuai permintaan
                close_last = data['Close'].iloc[-1]  # Harga Close terakhir

                # Hitung skor 3 hari terakhir (1 = naik, -1 = turun, 0 = stagnan)
                price_changes = data['Close'].diff().tail(3)
                score = price_changes.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)).sum()

                # Jika semua candle naik/turun, gunakan close terakhir
                if all(price_changes > 0) or all(price_changes < 0):
                    rk_base = close_last
                    sk_base = close_last
                else:
                     rk_base = ath_value
                     sk_base = atl_value

               # Hitung ATR
                high_low = data['High'] - data['Low']
                high_close = (data['High'] - data['Close'].shift()).abs()
                low_close = (data['Low'] - data['Close'].shift()).abs()
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean()

                # Sesuaikan RK & SK berdasarkan skor
                if score > 0:
                  direction_factor = 1  # Naik
                elif score < 0:
                  direction_factor = -1  # Turun
                else:
                   direction_factor = 0  # Netral

                rk_adjusted = rk_base + (atr.iloc[-1] * multiplier * direction_factor)
                sk_adjusted = sk_base + (atr.iloc[-1] * multiplier * direction_factor)

#             Pastikan SK tidak 0 atau negatif
                if sk_adjusted <= 0:
                   sk_adjusted = close_last * 0.5
                support_dyn = atl_value - (atr.iloc[-1] * multiplier)
                resist_dyn = ath_value + (atr.iloc[-1] * multiplier)

                
                rsi_last = indicators['rsi'].iloc[-1]
                
                mas_last = [ma.iloc[-1] if ma is not None else None for ma in indicators['mas']]
                ma_caption = calculator.format_ma_caption(
                               current_price, mas_last, rsi_last, tf_name, support_dyn, resist_dyn
                           )

             
                charts.append((tf_name, chart_buffer, ma_caption))
                
                # Simpan score
                final_score_value = final_score.iloc[-1] if len(final_score) > 0 else 0
                timeframe_scores[tf_name] = final_score_value
                
                print(f"✅ {tf_name} completed with score: {final_score_value:.2f}")  # Debug log
                
            except Exception as e:
                print(f"❌ Error processing {tf_name}: {str(e)}")  # Debug log lebih detail
                import traceback
                traceback.print_exc()  # Print full traceback
                continue
            
        # Kirim charts
        if charts:
          await loading_msg.edit_text(f"✅ Analisis {symbol.replace('.JK', '')} selesai! Mengirim charts...")

          for tf_name, chart_buffer, ma_caption in charts:
              full_caption = f"📈 {symbol.replace('.JK', '')} - {tf_name} Analysis\n\n{ma_caption}"
              await update.message.reply_photo(
                photo=chart_buffer,
                caption=full_caption
             )
              del chart_buffer
              gc.collect() 
              await asyncio.sleep(0.9)  # jeda sebentar supaya RAM bebas

# Hitung average score setelah semua timeframe diproses
          combined_scores = list(timeframe_scores.values())
          if combined_scores:
            average_score = sum(combined_scores) / len(combined_scores)
          else:
            average_score = 0

          interpretation = ""
          if average_score > 5:
             interpretation = "🟢 Bullish Kuat"
          elif average_score > 2:
             interpretation = "🔵 Bullish"
          elif average_score > 0:
             interpretation = "🟡 Tenang"
          elif average_score > -2:
             interpretation = "🔴 Bearish"
          else:
            interpretation = "⚫ Bearish kuat"

          summary = f"""
📊 {symbol.replace('.JK', '')} Analysis Summary

📈 Nilai Harian {timeframe_scores.get('Daily', 0):.2f}
📈 Nilai Mingguan {timeframe_scores.get('Weekly', 0):.2f}  
📈 Nilai Bulanan {timeframe_scores.get('Monthly', 0):.2f}

🎯 Rata-rata Nilai: {average_score:.2f}
📈 Trend saham {symbol.replace('.JK', '')} adalah: {interpretation}

⚠️*Disclaimer: Ini hanya analisis teknikal dan bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
          """
          await update.message.reply_text(summary)
            
        else:
            await loading_msg.edit_text(f"❌ Gagal menganalisis {symbol.replace(".JK", "")}. Pastikan symbol valid.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        
    finally:
        if user_id in request_queue:
           request_queue.remove(user_id)

async def cmd_calculate_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("DEBUG: cmd_calculate_us called") 
    """Command handler untuk /us"""
    if not is_authorized_user(update):
        await update.message.reply_text(
            "Hi!! Maaf kamu tidak terdaftar sebagai member premium" "Jika ingin  bergabung menjadi member premium dan menggunakan bot sesuka hati bisa hubungi @Rendanggedang"
        )
        return
    try:
        # Parse argumen
        if not context.args:
            await update.message.reply_text("Gunakan: /us SYMBOL\nContoh: /us AAPL")
            return
        
        user_id = update.effective_user.id
        current_time = time.time()
        last_request_time = user_last_request[user_id]
    
        time_since_last = current_time - last_request_time
    
        if time_since_last < REQUEST_COOLDOWN:
            remaining_time = REQUEST_COOLDOWN - time_since_last
            await update.message.reply_text(
                f"⏳ Mohon tunggu {remaining_time:.1f} detik sebelum request berikutnya."
            )
            return
        
        request_queue.append(user_id)
        queue_position = list(request_queue).index(user_id) + 1

        if queue_position > 1:
           await update.message.reply_text(
               f"⏳ Anda berada di antrian ke [{queue_position}] harap bersabar..."
           )
        
        symbol = context.args[0].upper()

        # Kirim pesan loading
        loading_msg = await update.message.reply_text(f"📊 Menganalisis {symbol}...")
        
        # Timeframe dan periode
        timeframes = {
            'Daily': {'period': '1d', 'days': 40, 'download_days' : 250},
            'Weekly': {'period': '1wk', 'days': 10*7, 'download_days' : 25*7},  # 40 minggu
            'Monthly': {'period': '1mo', 'days': 10*30, 'download_days' : 15*30}  # 60 bulan
        }
        
        charts = []
        timeframe_scores = {}
   
        for tf_name, tf_config in timeframes.items():
            print(f"🔍 Processing {tf_name}...")  # Debug log
            try:
                # Download data
                end_date = datetime.now()
                
                if tf_name == 'Daily':
                    download_days = 250
                    display_days = 40
                elif tf_name == 'Weekly':
                    download_days = 25*7
                    display_days = 10*7
                else:  # Monthly
                    download_days = 15*30
                    display_days = 10*30
                
                start_date = end_date - timedelta(days=download_days)
                
                print(f"📊 Downloading {tf_name} data for {symbol}...")  # Debug log
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date, end=end_date, interval=tf_config['period'])
                # Update candle terakhir pakai harga live (hanya untuk Close)
                try:
                    live_data = ticker.history(period="1d", interval="1m")
                    if not live_data.empty:
                        live_close = live_data['Close'].iloc[-1]
                        data.iloc[-1, data.columns.get_loc('Close')] = live_close
                except Exception:
                   pass
                
                if data.empty:
                    print(f"❌ No data for {tf_name}")  # Debug log
                    continue
                
                print(f"✅ Data downloaded: {len(data)} rows for {tf_name}")  # Debug log
                
                # Hitung indikator
                print(f"🔢 Calculating indicators for {tf_name}...")  # Debug log
                final_score, indicators = calculator.calculate_final_formula(data, tf_name)
                print(f"✅ Indicators calculated for {tf_name}")  # Debug log
             
                # Potong data untuk display
                display_data = data.tail(display_days) if len(data) > display_days else data
                display_score = final_score.tail(display_days) if len(final_score) > display_days else final_score
                
                # Pastikan panjang sama
                min_length = min(len(display_data), len(display_score))
                display_data = display_data.tail(min_length)
                display_score = display_score.tail(min_length)
                
                print(f"📈 Creating chart for {tf_name}...")  # Debug log
                # Buat chart
                chart_buffer = calculator.create_chart(display_data, display_score, indicators, tf_name, symbol)
                current_price = data['Close'].iloc[-1]
                
                atl_value = data['Close'].min()
                ath_value = data['Close'].max()
                # Hitung ATR (volatilitas) untuk membuat Support & Resist dinamis
                high_low = data['High'] - data['Low']
                high_close = (data['High'] - data['Close'].shift()).abs()
                low_close = (data['Low'] - data['Close'].shift()).abs()
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean()

                multiplier = 1.07  # ATR multiplier sesuai permintaan
                close_last = data['Close'].iloc[-1]  # Harga Close terakhir

                # Hitung skor 3 hari terakhir (1 = naik, -1 = turun, 0 = stagnan)
                price_changes = data['Close'].diff().tail(3)
                score = price_changes.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)).sum()

                # Jika semua candle naik/turun, gunakan close terakhir
                if all(price_changes > 0) or all(price_changes < 0):
                    rk_base = close_last
                    sk_base = close_last
                else:
                     rk_base = ath_value
                     sk_base = atl_value

               # Hitung ATR
                high_low = data['High'] - data['Low']
                high_close = (data['High'] - data['Close'].shift()).abs()
                low_close = (data['Low'] - data['Close'].shift()).abs()
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean()

                # Sesuaikan RK & SK berdasarkan skor
                if score > 0:
                  direction_factor = 1  # Naik
                elif score < 0:
                  direction_factor = -1  # Turun
                else:
                   direction_factor = 0  # Netral

                rk_adjusted = rk_base + (atr.iloc[-1] * multiplier * direction_factor)
                sk_adjusted = sk_base + (atr.iloc[-1] * multiplier * direction_factor)

#             Pastikan SK tidak 0 atau negatif
                if sk_adjusted <= 0:
                   sk_adjusted = close_last * 0.5

                support_dyn = atl_value - (atr.iloc[-1] * multiplier)
                resist_dyn = ath_value + (atr.iloc[-1] * multiplier)
                
                rsi_last = indicators['rsi'].iloc[-1]
                
                mas_last = [ma.iloc[-1] if ma is not None else None for ma in indicators['mas']]
                ma_caption = calculator.format_ma_caption(
                              current_price, mas_last, rsi_last, tf_name, support_dyn, resist_dyn
                            )

                charts.append((tf_name, chart_buffer, ma_caption))
                
                # Simpan score
                final_score_value = final_score.iloc[-1] if len(final_score) > 0 else 0
                timeframe_scores[tf_name] = final_score_value
                
                print(f"✅ {tf_name} completed with score: {final_score_value:.2f}")  # Debug log
                
            except Exception as e:
                print(f"❌ Error processing {tf_name}: {str(e)}")  # Debug log lebih detail
                import traceback
                traceback.print_exc()  # Print full traceback
                continue
            
        # Kirim charts
        if charts:
          await loading_msg.edit_text(f"✅ Analisis {symbol} selesai! Mengirim charts...")

          for tf_name, chart_buffer, ma_caption in charts:
              full_caption = f"📈 {symbol} - {tf_name} Analysis\n\n{ma_caption}"
              await update.message.reply_photo(
                photo=chart_buffer,
                caption=full_caption
             )
              del chart_buffer
              gc.collect() 
              await asyncio.sleep(0.9)  # jeda sebentar supaya RAM bebas

# Hitung average score setelah semua timeframe diproses
          combined_scores = list(timeframe_scores.values())
          if combined_scores:
            average_score = sum(combined_scores) / len(combined_scores)
          else:
            average_score = 0

          interpretation = ""
          if average_score > 5:
             interpretation = "🟢 Bullish Kuat"
          elif average_score > 2:
             interpretation = "🔵 Bullish"
          elif average_score > 0:
             interpretation = "🟡 Tenang"
          elif average_score > -2:
             interpretation = "🔴 Bearish"
          else:
            interpretation = "⚫ Bearish kuat"

          summary = f"""
📊 {symbol} Analysis Summary

📈 Nilai Harian {timeframe_scores.get('Daily', 0):.2f}
📈 Nilai Minguan {timeframe_scores.get('Weekly', 0):.2f}  
📈 Nilai Bulanan {timeframe_scores.get('Monthly', 0):.2f}

🎯 Rata-rata Nilai: {average_score:.2f}
📈 Trend saham {symbol} adalah: {interpretation}

⚠️*Disclaimer: Ini hanya analisis teknikal dan bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
          """
          await update.message.reply_text(summary)
            
        else:
            await loading_msg.edit_text(f"❌ Gagal menganalisis {symbol}. Pastikan symbol valid.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        
    finally:
        if user_id in request_queue:
           request_queue.remove(user_id)
           
async def cmd_screener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /sc (screener KOMPAS1200 dengan skor Daily/Weekly/Monthly + pagination)"""
    if not is_authorized_user(update):
        await update.message.reply_text(
            "Hi!! Maaf kamu tidak terdaftar sebagai member premium." "Jika ingin  bergabung menjadi member premium dan menggunakan bot sesuka hati bisa hubungi @Rendanggedang"
        )
        return
    user_id = update.effective_user.id

    # Cek jika user sedang screener
    if user_busy_flags.get(user_id, False):
        await update.message.reply_text(
            "⏳ Proses sebelumnya masih berjalan. Mohon tunggu hingga selesai."
        )
        return
    
    # ✅ Cek apakah hasil screener masih ada di cache
    if user_screener_results.get(user_id):
        await update.message.reply_text("📂 Menampilkan data screener...")
        await send_screener_page(update, context, user_id, page=0)
        return 
    
    user_busy_flags[user_id] = True
    await update.message.reply_text("🔍 Memulai screening KOMPAS100... Harap tunggu beberapa menit.")

    komppas100_list = [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "ADRO.JK", "TLKM.JK", "ASII.JK", "ANTM.JK", "UNVR.JK", "INDF.JK", "ICBP.JK",
        "PGAS.JK", "PTBA.JK", "GGRM.JK", "BBNI.JK", "KLBF.JK", "ITMG.JK", "UNTR.JK", "JPFA.JK", "MYOR.JK", "GOTO.JK",
        "BRIS.JK", "CTRA.JK", "SMGR.JK", "JSMR.JK", "MNCN.JK", "CPIN.JK", "BSDE.JK", "PTPP.JK", "PWON.JK", "INTP.JK",
        "HRUM.JK", "SIDO.JK", "SMRA.JK", "BRPT.JK", "SCMA.JK", "BBTN.JK", "INCO.JK", "MEDC.JK", "LSIP.JK", "PTRO.JK",
        "HMSP.JK", "ACES.JK", "MDKA.JK", "TINS.JK", "EXCL.JK", "BRMS.JK", "INKP.JK", "ARTO.JK", "ADMR.JK", "PGEO.JK",
        "ELSA.JK", "PANI.JK", "AKRA.JK", "KIJA.JK", "INDY.JK", "TPIA.JK", "BNGA.JK", "ERAA.JK", "AMRT.JK", "ISAT.JK",
        "WIFI.JK", "TOWR.JK", "RAJA.JK", "EMTK.JK", "TKIM.JK", "BTPS.JK", "ENRG.JK", "GJTL.JK", "AMMN.JK", "ESSA.JK",
        "MAPI.JK", "SRTG.JK", "TOBA.JK", "MBMA.JK", "AUTO.JK", "BMTR.JK", "NISP.JK", "DEWA.JK", "BBYB.JK", "PNLF.JK",
        "MIKA.JK", "FILM.JK", "NCKL.JK", "BFIN.JK", "MAPA.JK", "MTEL.JK", "AXIA.JK", "SSIA.JK", "KPIG.JK", "INET.JK",
        "DSNG.JK", "SSMS.JK", "HEAL.JK", "MIDI.JK", "CMRY.JK", "SMIL.JK", "MARK.JK", "UNIQ.JK", "BDKR.JK", "SURI.JK"
    ]

    results = []

    try:
        for symbol in komppas100_list:
            try:
                ticker = yf.Ticker(symbol)
                timeframe_scores = {}

                timeframes = {
                    "Daily": {"period": "1d", "download_days": 250},
                    "Weekly": {"period": "1wk", "download_days": 25 * 7},
                    "Monthly": {"period": "1mo", "download_days": 15 * 30}
                }

                for tf_name, tf_config in timeframes.items():
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=tf_config["download_days"])
                    data = ticker.history(start=start_date, end=end_date, interval=tf_config["period"])

                    if data.empty or len(data) < 10:
                        timeframe_scores[tf_name] = 0
                        continue

                    final_score, _ = calculator.calculate_final_formula(data, tf_name)
                    timeframe_scores[tf_name] = final_score.iloc[-1] if not final_score.empty else 0

                    # Hapus DataFrame & RAM pressure
                    del data
                    gc.collect()

                avg_score = sum(timeframe_scores.values()) / len(timeframe_scores)
                
                if avg_score > 2:
                   results.append((symbol.replace(".JK", ""), timeframe_scores, avg_score))
                   print(f"✅ {symbol} Avg: {avg_score:.2f}")
                else:
                   print(f"❌ {symbol} di-skip (Avg: {avg_score:.2f})")
                   
                # Simpan hanya skor & teks
                results.append((symbol.replace(".JK", ""), timeframe_scores, avg_score))

                print(f"✅ {symbol} Avg: {avg_score:.2f}")

                # Jeda antar saham untuk hemat resource
                await asyncio.sleep(1.5)

            except Exception as e:
                print(f"❌ Error pada {symbol}: {e}")
                continue

        # Simpan hasil ke cache user
        user_screener_results[user_id] = results
        user_screener_page[user_id] = 0

        await send_screener_page(update, context, user_id, page=0)

    finally:
        user_busy_flags[user_id] = False
        
async def send_screener_page(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, page: int):
    """Kirim hasil screener dalam halaman dengan tombol Next/Prev"""
    results = user_screener_results[user_id]
    page_size = 10
    total_pages = (len(results) + page_size - 1) // page_size

    # Potong hasil
    start = page * page_size
    end = start + page_size
    page_results = results[start:end]

    text = f"📊 *Hasil Screener KOMPAS100* (Halaman {page+1}/{total_pages})\n\n"
    for i, (code, tf_scores, avg) in enumerate(page_results, start=1):
        text += (f"{start+i}. {code} | Daily: {tf_scores['Daily']:.2f} | "
                 f"Weekly: {tf_scores['Weekly']:.2f} | Monthly: {tf_scores['Monthly']:.2f} | "
                 f"Avg: {avg:.2f}\n")

    # Tombol navigasi
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data="prev_screener"))
    if end < len(results):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data="next_screener"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text=text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    user_screener_page[user_id] = page

async def screener_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol Next/Prev"""
    query = update.callback_query
    user_id = query.from_user.id
    current_page = user_screener_page[user_id]

    if query.data == "next_screener":
        current_page += 1
    elif query.data == "prev_screener":
        current_page -= 1

    await send_screener_page(update, context, user_id, current_page)
    
async def clear_screener_cache_daily():
    """Clear cache setiap hari jam 16:00 WIB"""
    while True:
        now = datetime.now(pytz.timezone('Asia/Jakarta'))
        target = now.replace(hour=16, minute=0, second=0, microsecond=0)

        if now >= target:
            # Kalau sudah lewat jam 16:00, set target ke besok
            target += timedelta(days=1)

        sleep_seconds = (target - now).total_seconds()
        print(f"🕒 Sleeping {sleep_seconds} detik sampai auto-clear cache...")

        await asyncio.sleep(sleep_seconds)

        user_screener_results.clear()
        user_screener_page.clear()
        print("♻️ Cache screener berhasil dibersihkan jam 16:00 WIB.")

async def post_init(app: Application):
    """Task yang berjalan setelah bot start"""
    print("🚀 Post init: menjalankan clear_screener_cache_daily()")
    app.create_task(clear_screener_cache_daily())
    
async def cmd_go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /go untuk cek IHSG dan spam notif cewek kalau merah"""
    if not is_authorized_user(update):
        await update.message.reply_text(
            "Hi sayang! 🥺 Kamu belum premium nih. Chat @Rendanggedang dulu biar bisa lanjut 😘"
        )
        return

    try:
        # Set timezone ke WIB
        now_wib = datetime.now(pytz.timezone("Asia/Jakarta"))
        current_hour = now_wib.hour
        current_minute = now_wib.minute
        current_day = now_wib.weekday()  # 0=Senin, 6=Minggu

        # Cek kalau hari Sabtu (5) atau Minggu (6)
        if current_day >= 5:
            await update.message.reply_text("📅 Market tutup sayang~ Sekarang weekend 💤")
            return

        # Cek apakah di luar jam trading
        if not ((9 <= current_hour < 12) or (13 <= current_hour < 16) or
                (current_hour == 12 and current_minute == 0) or
                (current_hour == 13 and current_minute >= 30)):
            await update.message.reply_text("🕘 Market lagi tutup sayang~ Kita mantau nanti pas jam trading 😴")
            return

        await update.message.reply_text("📡 Lagi mantau IHSG... tunggu ya sayang~ 😘")
        ticker = yf.Ticker("^JKSE")
        data = ticker.history(period="1d", interval="10m")

        if data.empty:
            await update.message.reply_text("❌ Gak bisa ambil data IHSG. Market mungkin lagi break 😅")
            return

        last_close = data["Close"].iloc[-1]
        prev_close = data["Close"].iloc[0]
        change_pct = ((last_close - prev_close) / prev_close) * 100

        if change_pct < -0.3:
            # Cari semua file gambar di folder
            img_folder = "/home/ec2-user/img"
            img_files = [f for f in os.listdir(img_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

            if not img_files:
                await update.message.reply_text("❌ Gak ada foto cewek di folder img 😭")
                return

            # Spam 5x dengan foto random
            for _ in range(5):
                random_img = random.choice(img_files)
                img_path = os.path.join(img_folder, random_img)
                await update.message.reply_photo(
                    photo=open(img_path, 'rb'),
                    caption=f"😡 Sayang!! IHSG {change_pct:.2f}% 🔻\nBURUAN JUAL!! Jangan bandel kayak kemarin ya 😤"
                )
                await asyncio.sleep(1.5)  # jeda biar gak kena rate limit Telegram
        else:
            await update.message.reply_text(f"✅ IHSG masih aman sayang~ 🟢 {change_pct:.2f}%")

    except Exception as e:
        await update.message.reply_text(f"❌ Error di /go: {e}")

def main():
    """Fungsi utama"""
    # Buat aplikasi
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Tambahkan handler
    app.add_handler(CommandHandler("c", cmd_calculate))
    app.add_handler(CommandHandler("us", cmd_calculate_us))
    app.add_handler(CommandHandler("sc", cmd_screener))
    app.add_handler(CommandHandler("go", cmd_go))
    app.add_handler(CallbackQueryHandler(screener_callback, pattern="^(next_screener|prev_screener)$"))  
    async def handle_unauthorized_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unauthorized messages"""
        if not is_authorized_user(update):
            await update.message.reply_text(
                "Hi!! Maaf kamu tidak terdaftar sebagai member premium." "Jika ingin  bergabung menjadi member premium dan menggunakan bot sesuka hati bisa hubungi @Rendanggedang"
            )

       # Tambahkan handler ini di main() sebelum app.run_polling():
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unauthorized_message))
    

    # Jalankan bot
    print("🤖 Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
    
