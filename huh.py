import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
import io
import asyncio
from datetime import datetime, timedelta

# Token bot Telegram (ganti dengan token bot Anda)
BOT_TOKEN = "7658203603:AAG5wnXwTLPN5qhxcpHiIA7QL19j1lSkPEA"

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
    
    def calculate_m_value(self, macd_line, signal_line, histogram):
        """Menghitung nilai M (MACD combined)"""
        # M = macd_line + signal_line (simplified interpretation)
        m_combined = macd_line + signal_line
        
        # Konversi ke nilai diskrit
        m_values = []
        for val in m_combined:
            if pd.isna(val):
                m_values.append(0)
            elif -25 <= val <= 25:
                m_values.append(0)
            elif val > 10:
                m_values.append(1)
            elif val < -10:
                m_values.append(-1)
            else:
                m_values.append(0)
        
        return pd.Series(m_values, index=m_combined.index)
    
    def calculate_s_value(self, k_percent, d_percent):
        """Menghitung nilai S (Stochastic combined)"""
        s_combined = k_percent + d_percent
        
        s_values = []
        for val in s_combined:
            if pd.isna(val):
                s_values.append(0)
            elif 0 <= val <= 60:
                s_values.append(1)
            elif 60 < val <= 70:
                s_values.append(0)
            elif val > 85:
                s_values.append(-1)
            else:
                s_values.append(0)
        
        return pd.Series(s_values, index=s_combined.index)
    
    def calculate_price_changes(self, data):
        """Menghitung perubahan harga 1, 2, 3 hari"""
        close_prices = data['Close']
        
        # Kenaikan (ku)
        ku1 = []
        ku2 = []
        ku3 = []
        
        # Penurunan (kd)
        kd1 = []
        kd2 = []
        kd3 = []
        
        for i in range(len(close_prices)):
            # ku1 (1 hari)
            if i >= 1:
                change = close_prices.iloc[i] - close_prices.iloc[i-1]
                if change > 0:
                    ku1.append(1)
                    kd1.append(-1)
                elif change < 0:
                    ku1.append(-1)
                    kd1.append(1)
                else:
                    ku1.append(0)
                    kd1.append(0)
            else:
                ku1.append(0)
                kd1.append(0)
            
            # ku2 (2 hari)
            if i >= 2:
                change = close_prices.iloc[i] - close_prices.iloc[i-2]
                if change > 0:
                    ku2.append(1)
                    kd2.append(-1)
                elif change < 0:
                    ku2.append(-1)
                    kd2.append(1)
                else:
                    ku2.append(0)
                    kd2.append(0)
            else:
                ku2.append(0)
                kd2.append(0)
            
            # ku3 (3 hari)
            if i >= 3:
                change = close_prices.iloc[i] - close_prices.iloc[i-3]
                if change > 0:
                    ku3.append(1)
                    kd3.append(-1)
                elif change < 0:
                    ku3.append(-1)
                    kd3.append(1)
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
    
    def calculate_signal_changes(self, macd_line, signal_line, k_percent, d_percent):
        """Menghitung perubahan sinyal MACD dan Stochastic"""
        # mup - sinyal MACD naik
        mup = []
        mdn = []
        
        for i in range(len(signal_line)):
            if i >= 1:
                change = signal_line.iloc[i] - signal_line.iloc[i-1]
                macd_val = macd_line.iloc[i]
                
                if change > 0:  # Naik
                    if -25 <= macd_val <= 25:
                        mup.append(0)
                        mdn.append(0)
                    else:
                        mup.append(1)
                        mdn.append(0)
                elif change < 0:  # Turun
                    if -25 <= macd_val <= 25:
                        mup.append(0)
                        mdn.append(0)
                    else:
                        mup.append(0)
                        mdn.append(-1)
                else:  # Sideways
                    mup.append(0)
                    mdn.append(0)
            else:
                mup.append(0)
                mdn.append(0)
        
        # sup - sinyal Stochastic naik
        sup = []
        sdn = []
        
        stoch_combined = k_percent + d_percent
        
        for i in range(len(k_percent)):
            if i >= 1:
                k_change = k_percent.iloc[i] - k_percent.iloc[i-1]
                stoch_val = stoch_combined.iloc[i]
                
                if k_change > 0:  # Naik
                    if 0 <= stoch_val <= 60:
                        sup.append(1)
                        sdn.append(0)
                    elif 60 < stoch_val <= 70:
                        sup.append(0)
                        sdn.append(0)
                    elif stoch_val > 85:
                        sup.append(-1)
                        sdn.append(0)
                    else:
                        sup.append(0)
                        sdn.append(0)
                elif k_change < 0:  # Turun
                    if 0 <= stoch_val <= 60:
                        sup.append(0)
                        sdn.append(-1)
                    elif 60 < stoch_val <= 70:
                        sup.append(0)
                        sdn.append(0)
                    elif stoch_val > 85:
                        sup.append(0)
                        sdn.append(1)
                    else:
                        sup.append(0)
                        sdn.append(0)
                else:  # Sideways
                    sup.append(0)
                    sdn.append(0)
            else:
                sup.append(0)
                sdn.append(0)
        
        return (pd.Series(mup, index=signal_line.index),
                pd.Series(mdn, index=signal_line.index),
                pd.Series(sup, index=k_percent.index),
                pd.Series(sdn, index=k_percent.index))
    
    def calculate_combined_trend(self, m_values, s_values):
        """Menghitung trend gabungan m dan s"""
        m_gt_s = []
        m_lt_s = []
        msdn = []
        
        for i in range(len(m_values)):
            if i >= 1:
                m_curr, m_prev = m_values.iloc[i], m_values.iloc[i-1]
                s_curr, s_prev = s_values.iloc[i], s_values.iloc[i-1]
                
                # (m>s) comparison
                if m_curr > s_curr:
                    m_gt_s.append(1)
                    m_lt_s.append(0)
                elif m_curr < s_curr:
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
                elif m_trend > 0 and s_trend > 0:  # Naik bersamaan
                    msdn.append(-1)
                else:  # Tidak bersamaan
                    msdn.append(0)
            else:
                m_gt_s.append(0)
                m_lt_s.append(0)
                msdn.append(0)
        
        return (pd.Series(m_gt_s, index=m_values.index),
                pd.Series(m_lt_s, index=m_values.index),
                pd.Series(msdn, index=m_values.index))
    
    def calculate_final_formula(self, data):
        """Menghitung rumus final"""
        # Hitung indikator
        macd_line, signal_line, histogram = self.calculate_macd(data)
        k_percent, d_percent = self.calculate_stochastic(data)
        
        # Hitung nilai M dan S
        m_values = self.calculate_m_value(macd_line, signal_line, histogram)
        s_values = self.calculate_s_value(k_percent, d_percent)
        
        # Hitung perubahan harga
        ku1, ku2, ku3, kd1, kd2, kd3 = self.calculate_price_changes(data)
        
        # Hitung perubahan sinyal
        mup, mdn, sup, sdn = self.calculate_signal_changes(macd_line, signal_line, k_percent, d_percent)
        
        # Hitung trend gabungan
        m_gt_s, m_lt_s, msdn = self.calculate_combined_trend(m_values, s_values)
        
        # Rumus final: (m>s)+mup+sup+ku1+ku2+2*ku3-kd1-kd2-2*kd3-mdn-sdn-(m<s)-msdn
        final_score = (m_gt_s + mup + sup + ku1 + ku2 + 2*ku3 - 
                      kd1 - kd2 - 2*kd3 - mdn - sdn - m_lt_s - msdn)
        
        return final_score, {
            'macd_line': macd_line,
            'signal_line': signal_line,
            'histogram': histogram,
            'k_percent': k_percent,
            'd_percent': d_percent,
            'm_values': m_values,
            's_values': s_values
        }
    
    def create_chart(self, data, final_score, indicators, timeframe, symbol):
        """Membuat chart hanya untuk final score"""
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        
        # Hanya tampilkan Final Score
        ax.plot(data.index, final_score, label='Final Score', color='red', linewidth=2)
        ax.fill_between(data.index, final_score, alpha=0.3, color='red')
        
        # Tambahkan garis referensi
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax.axhline(y=5, color='green', linestyle='--', alpha=0.7, label='Strong Buy Level')
        ax.axhline(y=2, color='lightgreen', linestyle='--', alpha=0.7, label='Buy Level')
        ax.axhline(y=-2, color='orange', linestyle='--', alpha=0.7, label='Sell Level')
        ax.axhline(y=-5, color='red', linestyle='--', alpha=0.7, label='Strong Sell Level')
        
        ax.set_title(f'{symbol} - {timeframe} Trading Score', fontsize=16, fontweight='bold')
        ax.set_ylabel('Score', fontsize=12)
        ax.set_xlabel('Date', fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # Format tanggal
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(data)//10)))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        # Warna latar belakang berdasarkan level
        latest_score = final_score.iloc[-1] if len(final_score) > 0 else 0
        if latest_score > 5:
            ax.set_facecolor('#e8f5e8')  # Light green
        elif latest_score > 2:
            ax.set_facecolor('#f0f8f0')  # Very light green
        elif latest_score > -2:
            ax.set_facecolor('#fff8dc')  # Light yellow
        elif latest_score > -5:
            ax.set_facecolor('#ffe4e1')  # Light red
        else:
            ax.set_facecolor('#ffe0e0')  # Light red
        
        plt.tight_layout()
        
        # Simpan ke buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        
        return buffer

# Inisialisasi calculator
calculator = TradingIndicator()

async def cmd_calculate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /c"""
    try:
        # Parse argumen
        if not context.args:
            await update.message.reply_text("Gunakan: /c SYMBOL\nContoh: /c AAPL")
            return
        
        symbol = context.args[0].upper()
        
        # Kirim pesan loading
        loading_msg = await update.message.reply_text(f"📊 Menganalisis {symbol}...")
        
        # Timeframe dan periode
        timeframes = {
            'Daily': {'period': '1d', 'days': 15},
            'Weekly': {'period': '1wk', 'days': 5*7},  # 40 minggu
            'Monthly': {'period': '1mo', 'days': 2*30}  # 60 bulan
        }
        
        charts = []
        
        for tf_name, tf_config in timeframes.items():
            try:
                # Download data
                end_date = datetime.now()
                start_date = end_date - timedelta(days=tf_config['days'])
                
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date, end=end_date, interval=tf_config['period'])
                
                if data.empty:
                    continue
                
                # Hitung indikator
                final_score, indicators = calculator.calculate_final_formula(data)
                
                # Buat chart
                chart_buffer = calculator.create_chart(data, final_score, indicators, tf_name, symbol)
                charts.append((tf_name, chart_buffer))
                
            except Exception as e:
                print(f"Error processing {tf_name}: {e}")
                continue
        
        # Kirim charts
        if charts:
            await loading_msg.edit_text(f"✅ Analisis {symbol} selesai! Mengirim charts...")
            
            for tf_name, chart_buffer in charts:
                await update.message.reply_photo(
                    photo=chart_buffer,
                    caption=f"📈 {symbol} - {tf_name} Analysis"
                )
            
            # Kirim ringkasan
            latest_score = final_score.iloc[-1] if len(final_score) > 0 else 0
            
            interpretation = ""
            if latest_score > 5:
                interpretation = "🟢 STRONG BUY"
            elif latest_score > 2:
                interpretation = "🔵 BUY"
            elif latest_score > -2:
                interpretation = "🟡 HOLD"
            elif latest_score > -5:
                interpretation = "🔴 SELL"
            else:
                interpretation = "⚫ STRONG SELL"
            
            summary = f"""
📊 **{symbol} Analysis Summary**

🎯 **Nilai*: {latest_score:.2f}
📈 **Recommendation**: {interpretation}

⚠️ **Disclaimer**: Ini hanya analisis teknikal dan bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
            """
            
            await update.message.reply_text(summary, parse_mode='Markdown')
            
        else:
            await loading_msg.edit_text(f"❌ Gagal menganalisis {symbol}. Pastikan symbol valid.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

def main():
    """Fungsi utama"""
    # Buat aplikasi
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Tambahkan handler
    app.add_handler(CommandHandler("c", cmd_calculate))
    
    # Jalankan bot
    print("🤖 Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
