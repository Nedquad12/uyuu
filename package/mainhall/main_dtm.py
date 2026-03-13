from utils import is_authorized_user
from state import with_queue_control, vip, spy
from cachescreener import user_screener_page, user_screener_results
from datetime import datetime, timedelta
from rate_limiter import with_rate_limit
import pandas as pd
import gc
import asyncio
from telegram.ext import ContextTypes
import time
import yfinance as yf
import sys
sys.path.append ("/home/ec2-user/package/machine")
from dtm import TradingIndicator
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update

def format_as_code_block(text: str) -> str:
    return f"```\n{text.strip()}\n```"

calculator = TradingIndicator()

@is_authorized_user
@spy
@with_queue_control
@with_rate_limit 
async def cmd_calculate1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /c"""
    try:
        # Parse argumen
        if not context.args:
            await update.message.reply_text("Gunakan: /c SYMBOL\nContoh: /c BBCA")
            return
        
        symbol = context.args[0].upper()

     # Auto-add .JK for Indonesian stocks if not already present
        if not ('.' in symbol or symbol.endswith('.JK')):
           symbol += '.JK'
        
        # Kirim pesan loading
        loading_msg = await update.message.reply_text(f"📊 Menganalisis {symbol.replace('.JK', '')}...")
        
        # Timeframe dan periode
        timeframes = {
            'Daily': {'period': '1d', 'days': 100, 'download_days' : 230},
            'Weekly': {'period': '1wk', 'days': 100*7, 'download_days' : 130*7},  # 40 minggu
            'Monthly': {'period': '1mo', 'days': 90*30, 'download_days' : 92*30}  # 60 bulan
        }
        
        charts = []
        timeframe_scores = {}
       
        for tf_name, tf_config in timeframes.items():
            print(f"🔍 Processing {tf_name}...")  # Debug log
            try:
                # Download data
                end_date = datetime.now()
                
                if tf_name == 'Daily':
                    download_days = 230
                    display_days = 100
                elif tf_name == 'Weekly':
                    download_days = 130*7
                    display_days = 100*7
                else:  # Monthly
                    download_days = 92*30
                    display_days = 90*30
                
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

📈 Harian {timeframe_scores.get('Daily', 0):.2f}
📈 Mingguan {timeframe_scores.get('Weekly', 0):.2f}  
📈 Bulanan {timeframe_scores.get('Monthly', 0):.2f}

🎯 Rata-rata: {average_score:.2f}
📈 Trend saham {symbol.replace('.JK', '')} adalah: {interpretation}

⚠️*Disclaimer: Ini hanya analisis teknikal dan bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
          """
          await update.message.reply_text(summary)
            
        else:
            await loading_msg.edit_text(f"❌ Gagal menganalisis {symbol.replace('.JK', '')}. Pastikan symbol valid.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@is_authorized_user
@spy
@vip
@with_queue_control
async def cmd_calculate_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("DEBUG: cmd_calculate_us called") 
    """Command handler untuk /us"""
    try:
        # Parse argumen
        if not context.args:
            await update.message.reply_text("Gunakan: /us SYMBOL\nContoh: /us AAPL")
            return
        
        symbol = context.args[0].upper()

        # Kirim pesan loading
        loading_msg = await update.message.reply_text(f"📊 Menganalisis {symbol}...")
        
        # Timeframe dan periode
        timeframes = {
            'Daily': {'period': '1d', 'days': 100, 'download_days' : 230},
            'Weekly': {'period': '1wk', 'days': 100*7, 'download_days' : 130*7},  # 40 minggu
            'Monthly': {'period': '1mo', 'days': 90*30, 'download_days' : 92*30}  # 60 bulan
        }
        
        charts = []
        timeframe_scores = {}
       
        for tf_name, tf_config in timeframes.items():
            print(f"🔍 Processing {tf_name}...")  # Debug log
            try:
                # Download data
                end_date = datetime.now()
                
                if tf_name == 'Daily':
                    download_days = 230
                    display_days = 100
                elif tf_name == 'Weekly':
                    download_days = 130*7
                    display_days = 100*7
                else:  # Monthly
                    download_days = 92*30
                    display_days = 90*30
                
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

📈 Harian {timeframe_scores.get('Daily', 0):.2f}
📈 Mingguan {timeframe_scores.get('Weekly', 0):.2f}  
📈 Bulanan {timeframe_scores.get('Monthly', 0):.2f}

🎯 Rata-rata: {average_score:.2f}
📈 Trend saham {symbol} adalah: {interpretation}

⚠️*Disclaimer: Ini hanya analisis teknikal dan bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
          """
          await update.message.reply_text(summary)
            
        else:
            await loading_msg.edit_text(f"❌ Gagal menganalisis {symbol}. Pastikan symbol valid.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@is_authorized_user
@spy
@vip
@with_queue_control
async def cmd_calculate_ksa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /ksa"""
    try:
        # Parse argumen
        if not context.args:
            await update.message.reply_text("Gunakan: /ksa SYMBOL\nContoh: /ksa 2222")
            return
        
        symbol = context.args[0].upper()

        if not ('.' in symbol or symbol.endswith('.SR')):
           symbol += '.SR'
        
        # Kirim pesan loading
        loading_msg = await update.message.reply_text(f"📊 Menganalisis {symbol.replace('.SR', '')}...")
        
        # Timeframe dan periode
        timeframes = {
            'Daily': {'period': '1d', 'days': 100, 'download_days' : 230},
            'Weekly': {'period': '1wk', 'days': 90*7, 'download_days' : 130*7},  # 40 minggu
            'Monthly': {'period': '1mo', 'days': 90*30, 'download_days' : 92*30}  # 60 bulan
        }
        
        charts = []
        timeframe_scores = {}
       
        for tf_name, tf_config in timeframes.items():
            print(f"🔍 Processing {tf_name}...")  # Debug log
            try:
                # Download data
                end_date = datetime.now()
                
                if tf_name == 'Daily':
                    download_days = 200
                    display_days = 100
                elif tf_name == 'Weekly':
                    download_days = 129*7
                    display_days = 90*7
                else:  # Monthly
                    download_days = 90*30
                    display_days = 90*30
                
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
          await loading_msg.edit_text(f"✅ Analisis {symbol.replace('.SR', '')} selesai! Mengirim charts...")

          for tf_name, chart_buffer, ma_caption in charts:
              full_caption = f"📈 {symbol.replace('.SR', '')} - {tf_name} Analysis\n\n{ma_caption}"
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
📊 {symbol.replace('.SR', '')} Analysis Summary

📈 Harian {timeframe_scores.get('Daily', 0):.2f}
📈 Mingguan {timeframe_scores.get('Weekly', 0):.2f}  
📈 Bulanan {timeframe_scores.get('Monthly', 0):.2f}

🎯 Rata-rata: {average_score:.2f}
📈 Trend saham {symbol.replace('.SR', '')} adalah: {interpretation}

⚠️*Disclaimer: Ini hanya analisis teknikal dan bukan saran investasi. Selalu lakukan riset mandiri sebelum berinvestasi.
          """
          await update.message.reply_text(summary)
            
        else:
            await loading_msg.edit_text(f"❌ Gagal menganalisis {symbol.replace('.SR', '')}. Pastikan symbol valid.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

@is_authorized_user
@spy
@vip   
@with_queue_control        
async def cmd_screener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /screen133 (screener KOMPAS1200 dengan skor Daily/Weekly/Monthly + pagination)"""
    user_id = update.effective_user.id
    
    if user_screener_results.get(user_id):
        await update.message.reply_text("📂 Menampilkan data screener...")
        await send_screener_page(update, context, user_id, page=0)
        return 
    
    await update.message.reply_text("🔍 Memulai screening KOMPAS100... Harap tunggu beberapa menit.")

    komppas100_list = [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "ADRO.JK", "TLKM.JK", "ASII.JK", "ANTM.JK", "UNVR.JK", "INDF.JK", "ICBP.JK",
        "PGAS.JK", "PTBA.JK", "GGRM.JK", "BBNI.JK", "KLBF.JK", "ITMG.JK", "UNTR.JK", "JPFA.JK", "MYOR.JK", "GOTO.JK",
        "BRIS.JK", "CTRA.JK", "SMGR.JK", "JSMR.JK", "MNCN.JK", "CPIN.JK", "BSDE.JK", "PTPP.JK", "PWON.JK", "INTP.JK",
        "HRUM.JK", "SIDO.JK", "SMRA.JK", "BRPT.JK", "SCMA.JK", "BBTN.JK", "INCO.JK", "MEDC.JK", "LSIP.JK", "PTRO.JK",
        "HMSP.JK", "ACES.JK", "MDKA.JK", "TINS.JK", "EXCL.JK", "BRMS.JK", "INKP.JK", "ARTO.JK", "ADMR.JK", "PGEO.JK",
        "ELSA.JK", "PANI.JK", "AKRA.JK", "KIJA.JK", "INDY.JK", "TPIA.JK", "BNGA.JK", "ERAA.JK", "AMRT.JK", "ISAT.JK",
        "TCPI.JK", "TOWR.JK", "RAJA.JK", "EMTK.JK", "TKIM.JK", "BTPS.JK", "ENRG.JK", "GJTL.JK", "AMMN.JK", "ESSA.JK",
        "MAPI.JK", "SRTG.JK", "STAA.JK", "MBMA.JK", "AUTO.JK", "ASRI.JK", "NISP.JK", "DEWA.JK", "BBYB.JK", "PNLF.JK",
        "MIKA.JK", "FILM.JK", "NCKL.JK", "BFIN.JK", "MAPA.JK", "MTEL.JK", "AXIA.JK", "SSIA.JK", "KPIG.JK", "BUKA.JK",
        "DSNG.JK", "PNBN.JK", "HEAL.JK", "CLEO.JK", "CMRY.JK", "DSSA.JK", "BUMI.JK", "TAPG.JK", "AADI.JK", "SMDR.JK"
    ]

    results = []

    for symbol in komppas100_list:
        try:
            ticker = yf.Ticker(symbol)
            timeframe_scores = {}

            timeframes = {
                "Daily": {"period": "1d", "download_days": 200},
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
                
            if avg_score > 1:
                results.append((symbol.replace(".JK", ""), timeframe_scores, avg_score))
                print(f"✅ {symbol} Avg: {avg_score:.2f}")
            else:
                print(f"❌ {symbol} di-skip (Avg: {avg_score:.2f})")

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
        
async def send_screener_page(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, page: int):
    """Kirim hasil screener dalam halaman dengan tombol Next/Prev"""
    results = user_screener_results[user_id]
    page_size = 10
    total_pages = (len(results) + page_size - 1) // page_size

    # Potong hasil
    start = page * page_size
    end = start + page_size
    page_results = results[start:end]

    text = f"*📊 Hasil Screener KOMPAS100* (Halaman {page+1}/{total_pages})\n"
    text += "```"  # buka blok kode

    text += "\nNo  Kode    Daily   Weekly  Monthly  Avg"
    text += "\n----------------------------------------"

    for i, (code, tf_scores, avg) in enumerate(page_results, start=1):
        text += f"\n{start+i:>2}  {code:<7} {tf_scores['Daily']:>6.2f}   {tf_scores['Weekly']:>6.2f}   {tf_scores['Monthly']:>7.2f}  {avg:>5.2f}"

    text += "\n```"  # tutup blok kode


    # Tombol navigasi
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data="prev_screener"))
    if end < len(results):
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data="next_screener"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None

    if update.callback_query:
        await update.callback_query.edit_message_text(
            format_as_code_block(text),
             reply_markup=reply_markup,
             parse_mode="Markdown"
        )  
    else:
        await update.message.reply_text(
           format_as_code_block(text),
           reply_markup=reply_markup,
           parse_mode="Markdown"
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