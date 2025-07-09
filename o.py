import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import glob
import os
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import logging

# Setup logging untuk debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fungsi untuk membaca data dari XLSX
def load_stock_data(folder_path, stock_code, max_files=200):
    try:
        files = sorted(glob.glob(f"{folder_path}/*.xlsx"), reverse=True)[:max_files]
        logger.info(f"Found {len(files)} files in {folder_path}")
        
        if not files:
            logger.warning(f"No Excel files found in {folder_path}")
            return None
        
        combined_data = []

        for file in files:
            try:
                df = pd.read_excel(file)
                logger.info(f"Successfully read {file}")
                
                # Cek apakah kolom yang dibutuhkan ada
                required_columns = ['Kode Saham', 'Penutupan']
                if not all(col in df.columns for col in required_columns):
                    logger.warning(f"Required columns missing in {file}. Available columns: {df.columns.tolist()}")
                    continue
                
                df_filtered = df[df['Kode Saham'] == stock_code]
                
                if df_filtered.empty:
                    logger.info(f"No data for {stock_code} in {file}")
                    continue
                
                df_selected = df_filtered[['Penutupan', 'Tertinggi', 'Terendah']].copy()
                df_selected.rename(columns={'Penutupan': 'Close', 'Tertinggi': 'High', 'Terendah': 'Low'}, inplace=True)
                
                # Ekstrak tanggal dari nama file (format ddmmyy)
                filename = os.path.basename(file)
                # Ambil 6 digit terakhir sebelum .xlsx (ddmmyy)
                date_str = filename.replace('.xlsx', '')[-6:]
                
                try:
                    # Konversi ddmmyy ke datetime
                    day = int(date_str[:2])
                    month = int(date_str[2:4])
                    year = int(date_str[4:6])
                    # Asumsi tahun 20xx jika < 50, 19xx jika >= 50
                    full_year = 2000 + year if year < 50 else 1900 + year
                    date = datetime(full_year, month, day)
                    logger.info(f"Parsed date: {date} from filename: {filename}")
                except ValueError as e:
                    logger.error(f"Invalid date format in filename: {filename}, error: {e}")
                    continue
                
                # Ambil kolom yang dibutuhkan dan tambahkan tanggal
                df_selected = df_filtered[['Penutupan', 'Tertinggi', 'Terendah']].copy()
                df_selected['Date'] = date
                df_selected.rename(columns={'Penutupan': 'Close', 'Tertinggi': 'High', 'Terendah': 'Low'}, inplace=True) 
                
                combined_data.append(df_selected)
                
            except Exception as e:
                logger.error(f"Error reading file {file}: {str(e)}")
                continue

        if not combined_data:
            logger.warning(f"No valid data found for {stock_code}")
            return None
        
        data = pd.concat(combined_data).drop_duplicates().sort_values('Date').set_index('Date')
        logger.info(f"Successfully loaded {len(data)} records for {stock_code}")
        return data
        
    except Exception as e:
        logger.error(f"Error in load_stock_data: {e}")
        return None

# Fungsi untuk menghitung indikator spesial
def calculate_special_indicator(data, chart_type="daily", mup=0, sup=0, ku1=0, ku2=0, ku3=0, 
                                kd1=0, kd2=0, kd3=0, mdn=0, sdn=0, msdn=0, multiplier=10):
        ema12 = data['Close'].ewm(span=12).mean()
        ema26 = data['Close'].ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()

        low14 = data['Low'].rolling(window=14).min()
        high14 = data['High'].rolling(window=14).max()
        k = 10 * ((data['Close'] - low14) / (high14 - low14))
        d = k.rolling(window=3).mean()
   
        m_total = ema12 + ema26 + signal
        m_score = m_total.apply(lambda x: 1 if x > 50 else (-1 if x < -50 else 0))
        s_total = k + d
        s_score = s_total.apply(lambda x: 1 if x > 10 else (-1 if x < -10 else 0))

        spesial_daily = []
        for i in range(len(data)):
            m_vs_s = 1 if m_score.iloc[i] > s_score.iloc[i] else (-1 if m_score.iloc[i] < s_score.iloc[i] else 0)
            m_less_s = 1 if m_score.iloc[i] < s_score.iloc[i] else 0

            skor = (
                m_vs_s
                + mup + sup + ku1 + ku2 + 2 * ku3
                - kd1 - kd2 - 2 * kd3
                - mdn - sdn - m_less_s - msdn
            )
            spesial_daily.append(skor * multiplier)

        data['Spesial_Daily'] = spesial_daily
    
        if chart_type == "weekly":
           data['Spesial_Weekly'] = pd.Series(spesial_daily, index=data.index).rolling(window=5).mean()
        elif chart_type == "monthly":
            data['Spesial_Monthly'] = pd.Series(spesial_daily, index=data.index).rolling(window=20).mean()
    
        return data

# Fungsi untuk membuat plot
def plot_special_chart(data, stock_code, chart_type="daily"):
    try:
        fig, axs = plt.subplots(1, 1, figsize=(12, 6))
        
        date_labels = [d.strftime('%d/%m') for d in data.index]
        
        if chart_type == "daily":
            axs.plot(date_labels, data['Spesial_Daily'], color='yellow', marker='o', linewidth=2, markersize=4)
            axs.set_title(f'{stock_code} - Spesial Daily', fontsize=14, fontweight='bold')
            latest_value = data['Spesial_Daily'].iloc[-1]
        elif chart_type == "weekly":
            axs.plot(date_labels, data['Spesial_Weekly'], color='cyan', marker='s', linewidth=2, markersize=4)
            axs.set_title(f'{stock_code} - Spesial Weekly', fontsize=14, fontweight='bold')
            latest_value = data['Spesial_Weekly'].iloc[-1]
        elif chart_type == "monthly":
            axs.plot(date_labels, data['Spesial_Monthly'], color='magenta', marker='^', linewidth=2, markersize=4)
            axs.set_title(f'{stock_code} - Spesial Monthly', fontsize=14, fontweight='bold')
            latest_value = data['Spesial_Monthly'].iloc[-1]
          
            axs.set_ylabel('Value', fontsize=12)
            axs.grid(True, alpha=0.3)
            axs.axhline(y=0, color='red', linestyle='--', alpha=0.5)
            axs.set_xlabel('Date', fontsize=12)
        
            # Rotate x-axis labels for better readability
            plt.setp(axs.get_xticklabels(), rotation=45, ha='right')
        
            plt.tight_layout()
            file_path = f"{stock_code}_special_chart.png"
            plt.savefig(file_path, dpi=300, bbox_inches='tight')
            plt.close()
        
            logger.info(f"Chart saved as {file_path}")
            return file_path, latest_value
        
    except Exception as e:
           logger.error(f"Error creating plot: {e}")
           return None, 0
       
        
# Command handler untuk Telegram
async def command_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:

        logger.info(f"Command /c received from user {update.effective_user.id}")
        
        if not context.args:
            await update.message.reply_text("⚠️ Format: /c [KODE_SAHAM]\n\nContoh: /c BBCA")
            return

        stock_code = context.args[0].upper()
        logger.info(f"Processing stock code: {stock_code}")
        
        # Kirim pesan loading
        loading_message = await update.message.reply_text(f"🔄 Memproses data untuk {stock_code}...")
        
        folder_path = "/home/nedquad12/uyuu/chart"
        
        # Cek apakah folder ada
        if not os.path.exists(folder_path):
            await loading_message.edit_text(f"❌ Folder data tidak ditemukan: {folder_path}")
            logger.error(f"Folder not found: {folder_path}")
            return
        
        # Tentukan max_files berdasarkan jenis chart
        max_files_map = {"daily": 20, "weekly": 60, "monthly": 200}
        
        values = {}
        chart_paths = {}
        
        for chart_type in ["daily", "weekly", "monthly"]:
            await loading_message.edit_text(f"📊 Memproses {chart_type} untuk {stock_code}...")
            
            data = load_stock_data(folder_path, stock_code, max_files=max_files_map[chart_type])
            if data is None or data.empty:
                continue
                
            data = calculate_special_indicator(data, chart_type=chart_type)
            chart_path, latest_value = plot_special_chart(data, stock_code, chart_type)
            
            if chart_path:
                chart_paths[chart_type] = chart_path
                values[chart_type] = latest_value
        
        # Kirim semua chart dengan caption
        for chart_type in ["daily", "weekly", "monthly"]:
            if chart_type in chart_paths:
                caption = f"📊 {stock_code} - {chart_type.title()}\n"
                caption += f"Daily: {values.get('daily', 'N/A'):.2f}\n"
                caption += f"Weekly: {values.get('weekly', 'N/A'):.2f}\n"
                caption += f"Monthly: {values.get('monthly', 'N/A'):.2f}"
                
                with open(chart_paths[chart_type], 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption=caption)
                
                os.remove(chart_paths[chart_type])
                
    except Exception as e:
        logger.error(f"Error in command_c: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan: {str(e)}")

# Fungsi untuk mendapatkan semua kode saham dari data
def get_all_stock_codes(folder_path):
    try:
        files = sorted(glob.glob(f"{folder_path}/*.xlsx"), reverse=True)
        all_stocks = set()
        
        # Ambil beberapa file terbaru untuk mencari semua kode saham
        for file in files[:10]:  # Cek 10 file terbaru
            try:
                df = pd.read_excel(file)
                if 'Kode Saham' in df.columns:
                    stocks = df['Kode Saham'].unique()
                    all_stocks.update(stocks)
            except Exception as e:
                logger.error(f"Error reading file {file}: {e}")
                continue
        
        logger.info(f"Found {len(all_stocks)} unique stock codes")
        return list(all_stocks)
        
    except Exception as e:
        logger.error(f"Error getting stock codes: {e}")
        return []

# Fungsi untuk menghitung rank saham
def calculate_stock_rank(folder_path):
    try:
        stock_codes = get_all_stock_codes(folder_path)
        if not stock_codes:
            return []
        
        ranked_stocks = []
        
        for stock_code in stock_codes:
            try:
                data = load_stock_data(folder_path, stock_code, max_files=50)
                if data is None or data.empty:
                    continue
                
                data = calculate_special_indicator(data)
                
                # Ambil nilai terbaru
                latest_data = data.iloc[-1]
                daily = latest_data['Spesial_Daily']
                weekly = latest_data['Spesial_Weekly']
                monthly = latest_data['Spesial_Monthly']
                
                # Hitung score berdasarkan nilai positif
                score = 0
                if daily > 0:
                    score += 1
                if weekly > 0:
                    score += 1
                if monthly > 0:
                    score += 1
                
                # Hanya ambil saham dengan score sempurna (3)
                if score == 3:
                    ranked_stocks.append({
                        'stock_code': stock_code,
                        'daily': daily,
                        'weekly': weekly,
                        'monthly': monthly,
                        'score': score,
                        'date': latest_data.name
                    })
                    
            except Exception as e:
                logger.error(f"Error processing {stock_code}: {e}")
                continue
        
        # Sort berdasarkan nilai daily tertinggi
        ranked_stocks.sort(key=lambda x: x['daily'], reverse=True)
        
        logger.info(f"Found {len(ranked_stocks)} stocks with perfect score")
        return ranked_stocks
        
    except Exception as e:
        logger.error(f"Error calculating stock rank: {e}")
        return []

# Command handler untuk rank saham
async def command_dd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"Command /dd received from user {update.effective_user.id}")
        
        # Kirim pesan loading
        loading_message = await update.message.reply_text("🔄 Menganalisis semua saham...")
        
        folder_path = "/home/nedquad12/uyuu/chart"
        
        # Cek apakah folder ada
        if not os.path.exists(folder_path):
            await loading_message.edit_text(f"❌ Folder data tidak ditemukan: {folder_path}")
            logger.error(f"Folder not found: {folder_path}")
            return
        
        # Update loading message
        await loading_message.edit_text("📊 Menghitung ranking saham...")
        
        ranked_stocks = calculate_stock_rank(folder_path)
        
        if not ranked_stocks:
            await loading_message.edit_text("❌ Tidak ada saham dengan nilai sempurna (Daily, Weekly, Monthly > 0)")
            return
        await loading_message.delete()
        # Buat pesan ranking
        message = "🏆 **RANKING SAHAM SEMPURNA**\n"
        message += "_(Daily, Weekly, Monthly > 0)_\n\n"
        
        for i, stock in enumerate(ranked_stocks[:20], 1):  # Tampilkan top 20
            daily = stock['daily']
            weekly = stock['weekly']
            monthly = stock['monthly']
            date = stock['date'].strftime('%d/%m/%Y')
            
            message += f"{i}. **{stock['stock_code']}**\n"
            message += f"   📈 Daily: {daily:.2f}\n"
            message += f"   📊 Weekly: {weekly:.2f}\n"
            message += f"   📅 Monthly: {monthly:.2f}\n"
            message += f"   🗓️ Date: {date}\n\n"
        
        if len(ranked_stocks) > 20:
            message += f"_... dan {len(ranked_stocks) - 20} saham lainnya_\n\n"
        
        message += f"📊 Total saham sempurna: {len(ranked_stocks)}\n"
        message += f"🕐 Diupdate: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        
        # Hapus pesan loading
        await loading_message.delete()
        
        # Kirim hasil ranking
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in command_dd: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan: {str(e)}")

# Setup Bot Telegram
TOKEN = "7658203603:AAGmTNYzK6n6Lm6-jJps6hHs-p7d5pWbLuw"

def main():
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Add command handlers
        app.add_handler(CommandHandler("c", command_c))
        app.add_handler(CommandHandler("dd", command_dd))
        
        logger.info("🤖 Bot is starting...")
        print("🤖 Bot is running...")
        
        # Run bot
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        print(f"❌ Error starting bot: {e}")

if __name__ == "__main__":
    main()
