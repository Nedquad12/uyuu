import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import glob
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Fungsi untuk membaca data dari XLSX
def load_stock_data(folder_path, stock_code, max_files=200):
    files = sorted(glob.glob(f"{folder_path}/*.xlsx"), reverse=True)[:max_files]
    combined_data = []

    for file in files:
        df = pd.read_excel(file)
        df = df[df['Kode Saham'] == stock_code][['Date', 'Penutupan']]
        df.rename(columns={'Penutupan': 'Close'}, inplace=True)
        combined_data.append(df)

    if not combined_data:
        return None
    
    data = pd.concat(combined_data).drop_duplicates().sort_values('Date').set_index('Date')
    return data

# Fungsi untuk menghitung indikator spesial
def calculate_special_indicator(data):
    ema12 = data['Close'].ewm(span=12).mean()
    ema26 = data['Close'].ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()

    low14 = data['Close'].rolling(window=14).min()
    high14 = data['Close'].rolling(window=14).max()
    k = 100 * ((data['Close'] - low14) / (high14 - low14))
    d = k.rolling(window=3).mean()

    m_total = ema12 + ema26 + signal
    m_score = m_total.apply(lambda x: 1 if x > 50 else (-1 if x < -50 else 0))
    s_total = k + d
    s_score = s_total.apply(lambda x: 1 if x > 10 else (-1 if x < -10 else 0))

    spesial_daily = []
    for i in range(len(data)):
        m_vs_s = 1 if m_score.iloc[i] > s_score.iloc[i] else (-1 if m_score.iloc[i] < s_score.iloc[i] else 0)
        skor = m_vs_s
        spesial_daily.append(skor * 10)

    data['Spesial_Daily'] = spesial_daily
    data['Spesial_Weekly'] = pd.Series(spesial_daily, index=data.index).rolling(window=5).mean()
    data['Spesial_Monthly'] = pd.Series(spesial_daily, index=data.index).rolling(window=20).mean()
    return data

# Fungsi untuk membuat plot
def plot_special_chart(data, stock_code):
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

    axs[0].plot(data.index.strftime('%d%m'), data['Spesial_Daily'], color='yellow', marker='o')
    axs[0].set_title(f'Spesial - Daily')
    axs[0].set_ylabel('Value')

    axs[1].plot(data.index.strftime('%d%m'), data['Spesial_Weekly'], color='cyan', marker='s')
    axs[1].set_title(f'Spesial - Weekly')
    axs[1].set_ylabel('Value')

    axs[2].plot(data.index.strftime('%d%m'), data['Spesial_Monthly'], color='magenta', marker='^')
    axs[2].set_title(f'Spesial - Monthly')
    axs[2].set_ylabel('Value')
    axs[2].set_xlabel('Date')

    plt.tight_layout()
    file_path = f"{stock_code}_special_chart.png"
    plt.savefig(file_path)
    plt.close()
    return file_path

# Command handler untuk Telegram
async def command_c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Ketik: /c [KODE_SAHAM]")
        return

    stock_code = context.args[0].upper()
    folder_path = "/home/nedquad12/uyuu/chart"
    data = load_stock_data(folder_path, stock_code)

    if data is None or data.empty:
        await update.message.reply_text(f"❌ Data untuk {stock_code} tidak ditemukan.")
        return

    data = calculate_special_indicator(data)
    chart_path = plot_special_chart(data, stock_code)

    await update.message.reply_photo(photo=InputFile(chart_path))

# Setup Bot Telegram
TOKEN = "7658203603:AAGmTNYzK6n6Lm6-jJps6hHs-p7d5pWbLuw"
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("c", command_c))

if __name__ == "__main__":
    print("🤖 Bot is running...")
    app.run_polling()
