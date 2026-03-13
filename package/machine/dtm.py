from impor import *

class TradingIndicator:
    
    def __init__(self):
        pass
    print("✅ DTM siap digunakan")
    
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
           ma3 = data['Close'].rolling(window=3).mean()
           ma5 = data['Close'].rolling(window=5).mean()
           ma10 = data['Close'].rolling(window=10).mean()
           ma20 = data['Close'].rolling(window=20).mean()
           ma60 = data['Close'].rolling(window=60).mean()
           ma90 = data['Close'].rolling(window=90).mean()
           ma120 = data['Close'].rolling(window=120).mean()
    
           return ma3, ma5, ma10, ma20, ma60, ma90, ma120
       
        elif timeframe == 'Weekly':
           ma3 = data['Close'].rolling(window=3).mean()
           ma5 = data['Close'].rolling(window=5).mean()
           ma10 = data['Close'].rolling(window=10).mean()
           ma20 = data['Close'].rolling(window=20).mean()
           ma60 = data['Close'].rolling(window=60).mean()
           ma90 = data['Close'].rolling(window=90).mean()
           ma120 = data['Close'].rolling(window=120).mean()
           
           return ma3, ma5, ma10, ma20, ma60, ma90, ma120
    
        elif timeframe == 'Monthly':
            ma3 = data['Close'].rolling(window=3).mean()
            ma5 = data['Close'].rolling(window=5).mean()
            ma10 = data['Close'].rolling(window=10).mean()
            ma20 = data['Close'].rolling(window=20).mean()
            ma60 = data['Close'].rolling(window=60).mean()
            ma90 = data['Close'].rolling(window=90).mean()
            
            return ma3, ma5, ma10, ma20, ma60, ma90
    
    def format_ma_caption(self, current_price, mas, rsi_value, timeframe, atl_value, ath_value):
        """Format caption untuk MA dan RSI"""
        def format_ma_value(ma_value):
            if pd.isna(ma_value):
                return "N/A"
            diff = ((ma_value - current_price) / ma_value) * 100
            sign = "+" if diff >= 0 else ""
            return f"{ma_value:.2f} ({sign}{diff:.2f}%)"

        caption = f"Price (Close): {current_price:.2f}\n"
        caption += f"RSI: {rsi_value:.2f}\n"
    
        if timeframe == 'Daily':
           caption += f"MA3: {format_ma_value(mas[0])}\n"
           caption += f"MA5: {format_ma_value(mas[1])}\n"
           caption += f"MA10: {format_ma_value(mas[2])}\n"
           caption += f"MA20: {format_ma_value(mas[3])}\n"
           caption += f"MA60: {format_ma_value(mas[4])}\n"
           caption += f"MA90: {format_ma_value(mas[5])}\n"
           caption += f"MA120: {format_ma_value(mas[6])}"
             
        elif timeframe == 'Weekly':
           caption += f"MA3: {format_ma_value(mas[0])}\n"
           caption += f"MA5: {format_ma_value(mas[1])}\n"
           caption += f"MA10: {format_ma_value(mas[2])}\n"
           caption += f"MA20: {format_ma_value(mas[3])}\n"
           caption += f"MA60: {format_ma_value(mas[4])}\n"
           caption += f"MA90: {format_ma_value(mas[5])}\n"
           caption += f"MA120: {format_ma_value(mas[6])}"
    
        elif timeframe == 'Monthly':
           caption += f"MA3: {format_ma_value(mas[0])}\n"
           caption += f"MA5: {format_ma_value(mas[1])}\n"
           caption += f"MA10: {format_ma_value(mas[2])}\n"
           caption += f"MA20: {format_ma_value(mas[3])}\n"
           caption += f"MA60: {format_ma_value(mas[4])}\n"
           caption += f"MA90: {format_ma_value(mas[5])}"

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
        """Membuat chart dengan mplfinance - dengan MA ditampilkan"""
    
        # Siapkan data untuk mplfinance
        chart_data = data.copy()
    
        # Hitung MA5 dari final_score untuk smoothing
        ma5_final_score = final_score.rolling(window=5).mean()
    
        # Setup market colors yang sama dengan price.py
        mc = mpf.make_marketcolors(up='g', down='r', inherit=True)
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=True)
    
        # Ambil MA dari indicators
        mas = indicators['mas']
        
        # Pastikan MA memiliki index yang sama dengan chart_data
        # Align semua MA dengan chart_data index
        aligned_mas = []
        for ma in mas:
            if ma is not None:
                # Reindex MA to match chart_data dan forward fill NaN values
                aligned_ma = ma.reindex(chart_data.index).fillna(method='ffill')
                aligned_mas.append(aligned_ma)
            else:
                aligned_mas.append(None)
        
        # Buat additional plots untuk MA dan final score
        ap_dict = []
        
        # Tambahkan MA ke chart utama (panel 0) dengan pengecekan None
        if timeframe == 'Daily':
            if len(aligned_mas) >= 6:
                if aligned_mas[1] is not None:  # MA5
                    ap_dict.append(mpf.make_addplot(aligned_mas[1], panel=0, color='orange', width=1, alpha=0.8, type='line'))
                if aligned_mas[2] is not None:  # MA10
                    ap_dict.append(mpf.make_addplot(aligned_mas[2], panel=0, color='blue', width=1, alpha=0.8, type='line'))
                if aligned_mas[3] is not None:  # MA20
                    ap_dict.append(mpf.make_addplot(aligned_mas[3], panel=0, color='red', width=1.5, alpha=0.8, type='line'))
                if aligned_mas[4] is not None:  # MA60
                    ap_dict.append(mpf.make_addplot(aligned_mas[4], panel=0, color='purple', width=1, alpha=0.7, type='line'))
                if aligned_mas[5] is not None:  # MA90
                    ap_dict.append(mpf.make_addplot(aligned_mas[5], panel=0, color='brown', width=1, alpha=0.7, type='line'))
                    
        elif timeframe == 'Weekly':
            if len(aligned_mas) >= 5:
                if aligned_mas[1] is not None:  # MA5
                    ap_dict.append(mpf.make_addplot(aligned_mas[1], panel=0, color='orange', width=1, alpha=0.8, type='line'))
                if aligned_mas[2] is not None:  # MA10
                    ap_dict.append(mpf.make_addplot(aligned_mas[2], panel=0, color='blue', width=1, alpha=0.8, type='line'))
                if aligned_mas[3] is not None:  # MA20
                    ap_dict.append(mpf.make_addplot(aligned_mas[3], panel=0, color='red', width=1.5, alpha=0.8, type='line'))
                if aligned_mas[4] is not None:  # MA60
                    ap_dict.append(mpf.make_addplot(aligned_mas[4], panel=0, color='purple', width=1, alpha=0.7, type='line'))
                    
        elif timeframe == 'Monthly':
            if len(aligned_mas) >= 4:
                if aligned_mas[1] is not None:  # MA5
                    ap_dict.append(mpf.make_addplot(aligned_mas[1], panel=0, color='orange', width=1, alpha=0.8, type='line'))
                if aligned_mas[2] is not None:  # MA10
                    ap_dict.append(mpf.make_addplot(aligned_mas[2], panel=0, color='blue', width=1, alpha=0.8, type='line'))
                if aligned_mas[3] is not None:  # MA20
                    ap_dict.append(mpf.make_addplot(aligned_mas[3], panel=0, color='red', width=1.5, alpha=0.8, type='line'))
        
        # Align final_score dengan chart_data index
        aligned_final_score = final_score.reindex(chart_data.index).fillna(0)
        aligned_ma5_final_score = ma5_final_score.reindex(chart_data.index).fillna(0)
        
        # Tambahkan final score ke panel 1
        ap_dict.extend([
            mpf.make_addplot(aligned_final_score, panel=1, color='red', width=2, 
                            ylabel='Final Score', type='line'),
            mpf.make_addplot(aligned_ma5_final_score, panel=1, color='blue', 
                            linestyle='--', width=1.5, type='line')
        ])
    
        # Tambahkan garis referensi untuk final score
        if len(aligned_final_score) > 0:
            ref_lines = [0, 5, 2, -2, -5]
            ref_colors = ['black', 'green', 'lightgreen', 'orange', 'red']
            ref_styles = ['-', '--', '--', '--', '--']
    
            for line, color, style in zip(ref_lines, ref_colors, ref_styles):
                ref_line_data = pd.Series([line] * len(aligned_final_score), index=chart_data.index)
                ap_dict.append(mpf.make_addplot(ref_line_data, 
                                              panel=1, color=color, 
                                              linestyle=style, alpha=0.7))
    
        # Buat chart dengan style yang konsisten dengan price.py
        fig, axes = mpf.plot(
            chart_data,
            type='candle',
            style=s,
            addplot=ap_dict,
            title=f'{symbol.replace(".JK", "").replace(".SR", "")} - {timeframe} Trading Analysis',
            figsize=(14, 10),  # Ukuran lebih besar untuk menampung MA
            returnfig=True,
            tight_layout=True
        )
    
        # Tambahkan legend untuk MA (panel 0 - price chart)
        if len(axes) > 0:
            ma_legend_elements = [
                plt.Line2D([0], [0], color='orange', lw=1, label='MA5'),
                plt.Line2D([0], [0], color='blue', lw=1, label='MA10'),
                plt.Line2D([0], [0], color='red', lw=1.5, label='MA20'),
            ]
            
            if timeframe in ['Daily', 'Weekly']:
                ma_legend_elements.extend([
                    plt.Line2D([0], [0], color='purple', lw=1, label='MA60'),
                ])
                
            if timeframe == 'Daily':
                ma_legend_elements.extend([
                    plt.Line2D([0], [0], color='brown', lw=1, label='MA90'),
                ])
            
            axes[0].legend(handles=ma_legend_elements, loc='upper left', fontsize=9)
    
        # Tambahkan legend untuk final score indicators (panel 1)
        score_legend_elements = [
            plt.Line2D([0], [0], color='red', lw=2, label='Final Score'),
            plt.Line2D([0], [0], color='blue', lw=2, linestyle='--', label='MA5 Final Score'),
            plt.Line2D([0], [0], color='green', lw=1, linestyle='--', label='Bullish Zone (+5)'),
            plt.Line2D([0], [0], color='lightgreen', lw=1, linestyle='--', label='Positive (+2)'),
            plt.Line2D([0], [0], color='black', lw=1, linestyle='-', label='Neutral (0)'),
            plt.Line2D([0], [0], color='orange', lw=1, linestyle='--', label='Negative (-2)'),
            plt.Line2D([0], [0], color='red', lw=1, linestyle='--', label='Bearish Zone (-5)')
        ]
    
        if len(axes) > 1:
            axes[1].legend(handles=score_legend_elements, loc='upper left', fontsize=8)
    
        # Simpan ke buffer
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=300, bbox_inches='tight')  # DPI sama dengan price.py
        buffer.seek(0)
    
        # Cleanup
        plt.close(fig)
        plt.close('all')
        gc.collect()
    
        return buffer