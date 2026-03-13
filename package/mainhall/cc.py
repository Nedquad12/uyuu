import json
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
import io
import os
import gc
from rate_limiter import with_rate_limit
from utils import is_authorized_user
from state import with_queue_control, vip, spy

# Cache global untuk data
CHART_CACHE = {}
CACHE_DIR = "/home/ec2-user/database/cache"

def load_chart_data_to_cache():
    """Load semua file txt ke cache"""
    global CHART_CACHE
    CHART_CACHE.clear()
    
    cache_path = Path(CACHE_DIR)
    if not cache_path.exists():
        return False
    
    # Ambil semua file .txt
    txt_files = list(cache_path.glob("*.txt"))
    
    # Sort berdasarkan tanggal parsed, bukan nama file
    def get_file_date(file_path):
        try:
            filename = file_path.stem
            if len(filename) == 6 and filename.isdigit():
                day = int(filename[:2])
                month = int(filename[2:4])
                year = 2000 + int(filename[4:6])
                return datetime(year, month, day)
        except:
            pass
        return datetime.min
    
    # Sort dari yang terbaru ke terlama
    txt_files = sorted(txt_files, key=get_file_date, reverse=True)
    
    loaded_count = 0
    for file_path in txt_files[:400]:  # ✅ UBAH: Maksimal 400 file (dulu 202)
        try:
            # Parse tanggal dari nama file (ddmmyy.txt)
            filename = file_path.stem  # Tanpa .txt
            if len(filename) == 6 and filename.isdigit():
                day = filename[:2]
                month = filename[2:4]
                year = "20" + filename[4:6]
                date_str = f"{year}-{month}-{day}"
                
                # Load JSON
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                CHART_CACHE[date_str] = data
                loaded_count += 1
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            continue
    
    return loaded_count > 0

def get_stock_chart_data(ticker: str, days: int = 202) -> pd.DataFrame:
    """
    Ambil data saham dari cache untuk chart
    
    Args:
        ticker: Kode saham (contoh: BBCA)
        days: Jumlah hari data (default 202)
    
    Returns:
        DataFrame dengan kolom: Date, Open, High, Low, Close, Volume, Foreign_Net
    """
    if not CHART_CACHE:
        return None
    
    ticker = ticker.upper()
    chart_data = []
    
    # Ambil data dari cache (sudah sorted by date desc)
    for date_str in sorted(CHART_CACHE.keys(), reverse=True)[:days]:
        data = CHART_CACHE[date_str]
        
        try:
            # Cari index saham
            if ticker not in data.get('kode_saham', []):
                continue
            
            idx = data['kode_saham'].index(ticker)
            
            # Ambil data OHLCV
            open_price = data['first_trade'][idx]
            high_price = data['tertinggi'][idx]
            low_price = data['terendah'][idx]
            close_price = data['penutupan'][idx]
            volume = data['volume'][idx]
            foreign_sell = data['foreign_sell'][idx]
            foreign_buy = data['foreign_buy'][idx]
            
            # Skip jika data tidak valid
            if open_price == 0 or close_price == 0:
                continue
            
            # Hitung Foreign Net
            foreign_net = foreign_buy - foreign_sell
            
            chart_data.append({
                'Date': date_str,
                'Open': open_price,
                'High': high_price,
                'Low': low_price,
                'Close': close_price,
                'Volume': volume,
                'Foreign_Net': foreign_net
            })
        except (IndexError, KeyError, ValueError):
            continue
    
    if len(chart_data) < 2:
        return None
    
    # Buat DataFrame dan sort by date ascending
    df = pd.DataFrame(chart_data)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date')
    df.set_index('Date', inplace=True)
    
    return df

def create_candlestick_chart(ticker: str, days: int = 202) -> tuple:
    """
    Buat chart candlestick dengan MA dan Foreign Net
    
    Returns:
        tuple: (BytesIO chart, dict info harga)
    """
    df = get_stock_chart_data(ticker, days)
    if df is None or len(df) < 10:
        return None, None

    # Hitung MA sesuai panjang data
    ma_dict = {}
    ma_values = {}  # Simpan nilai MA terbaru
    
    if len(df) >= 10:
        df['MA10'] = df['Close'].rolling(window=10).mean()
        ma_dict['MA10'] = ('yellow', df['MA10'])
        ma_values['MA10'] = df['MA10'].iloc[-1]
    if len(df) >= 20:
        df['MA20'] = df['Close'].rolling(window=20).mean()
        ma_dict['MA20'] = ('green', df['MA20'])
        ma_values['MA20'] = df['MA20'].iloc[-1]
    if len(df) >= 60:
        df['MA60'] = df['Close'].rolling(window=60).mean()
        ma_dict['MA60'] = ('blue', df['MA60'])
        ma_values['MA60'] = df['MA60'].iloc[-1]
    if len(df) >= 120:
        df['MA120'] = df['Close'].rolling(window=120).mean()
        ma_dict['MA120'] = ('pink', df['MA120'])
        ma_values['MA120'] = df['MA120'].iloc[-1]
    if len(df) >= 200:
        df['MA200'] = df['Close'].rolling(window=200).mean()
        ma_dict['MA200'] = ('gold', df['MA200'])
        ma_values['MA200'] = df['MA200'].iloc[-1]

    # Hanya tampilkan 100 hari terakhir di chart
    df_display = df.tail(100).copy()

    # Info harga terbaru
    latest_data = df.iloc[-1]
    price_info = {
        'close': latest_data['Close'],
        'open': latest_data['Open'],
        'high': latest_data['High'],
        'low': latest_data['Low'],
        'volume': latest_data['Volume'],
        'foreign_net': latest_data['Foreign_Net'],
        'date': df.index[-1].strftime('%Y-%m-%d'),
        'ma_values': ma_values
    }

    # Warna foreign net (list, bukan Series)
    colors = ['green' if x >= 0 else 'red' for x in df_display['Foreign_Net']]

    mc = mpf.make_marketcolors(up='g', down='r', edge='inherit', wick='inherit', volume='in')
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle='-', gridcolor='gray', facecolor='white', figcolor='white')

    # Tambahkan MA yang tersedia
    apds = []
    for label, (color, series) in ma_dict.items():
        apds.append(mpf.make_addplot(series.tail(100), color=color, width=1, label=label))

    # Tambahkan foreign net bar (warna list)
    apds.append(
        mpf.make_addplot(df_display['Foreign_Net'], type='bar', color=colors, alpha=0.6,
                         panel=2, ylabel='Foreign Net')
    )

    fig, axes = mpf.plot(
        df_display,
        type='candle',
        style=s,
        title=f'{ticker} - Candlestick Chart (100 hari terakhir)',
        ylabel='Harga',
        volume=True,
        volume_panel=1,
        addplot=apds,
        panel_ratios=(3, 1, 1),
        figsize=(16, 10),
        returnfig=True,
        ylabel_lower='Volume',
        # Pindahkan angka ke kanan
        tight_layout=True
    )

    # Set y-axis ke kanan untuk semua panel
    for ax in axes:
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")

    # Legend hanya untuk MA yang aktif
    if ma_dict:
        axes[0].legend(ma_dict.keys(), loc='upper left', fontsize=8)

    # Simpan chart
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    gc.collect()  # bersihkan memori

    return buf, price_info

def format_price_caption(ticker: str, price_info: dict) -> str:
    """
    Format caption dengan info harga dan MA
    """
    caption = f"📊 *{ticker}* - {price_info['date']}\n\n"
    
    # Harga OHLC
    caption += f"💰 *Harga:*\n"
    caption += f"Close: {price_info['close']:,.0f}\n"
    caption += f"Open: {price_info['open']:,.0f}\n"
    caption += f"High: {price_info['high']:,.0f}\n"
    caption += f"Low: {price_info['low']:,.0f}\n\n"
    
    # Volume
    caption += f"📈 *Volume:* {price_info['volume']:,.0f}\n\n"
    
    # Moving Averages
    if price_info['ma_values']:
        caption += f"📉 *Moving Averages:*\n"
        for ma_name, ma_value in sorted(price_info['ma_values'].items()):
            if pd.notna(ma_value):
                diff = price_info['close'] - ma_value
                diff_pct = (diff / ma_value) * 100
                status = "🟢" if diff > 0 else "🔴"
                caption += f"{status} {ma_name}: {ma_value:,.0f} ({diff_pct:+.2f}%)\n"
        caption += "\n"
    
    # Foreign Net
    foreign_net = price_info['foreign_net']
    foreign_status = "🟢 NET BUY" if foreign_net >= 0 else "🔴 NET SELL"
    caption += f"🌍 *Foreign Net:* {foreign_status}\n"
    caption += f"   {abs(foreign_net):,.0f} lembar saham"
    
    return caption

@is_authorized_user
@spy
@with_queue_control
@with_rate_limit 
async def cc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command handler untuk /cc
    Usage: /cc BBCA
    """
    user_id = update.effective_user.id
    
    # Cek argumen
    if not context.args:
        await update.message.reply_text(
            "❌ Format salah!\n\n"
            "Gunakan: /cc <kode_saham>\n"
            "Contoh: /cc BBCA"
        )
        return
    
    ticker = context.args[0].upper()
    
    # Cek cache
    if not CHART_CACHE:
        await update.message.reply_text(
            "⚠️ Error"
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🔄 Membuat chart untuk {ticker}...\n"
        "Mohon tunggu sebentar..."
    )
    
    try:
        # Buat chart
        chart_buf, price_info = create_candlestick_chart(ticker, days=202)
        
        if chart_buf is None:
            await processing_msg.edit_text(
                f"❌ Data tidak ditemukan untuk {ticker}\n"
                "Pastikan kode saham benar atau IPO minimal 2 hari."
            )
            return
        
        # Format caption dengan info harga
        caption = format_price_caption(ticker, price_info)
        
        # Kirim chart
        await update.message.reply_photo(
            photo=chart_buf,
            caption=caption,
            parse_mode='Markdown'
        )
        
        # Hapus processing message
        await processing_msg.delete()
        
    except Exception as e:
        await processing_msg.edit_text(
            f"❌ Error membuat chart: {str(e)}"
        )

@is_authorized_user
@spy
@with_queue_control
@with_rate_limit 
async def reload10_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command handler untuk /reload10
    Load data chart ke cache
    """
    processing_msg = await update.message.reply_text(
        "🔄 Loading data chart ke cache...\n"
        "Mohon tunggu sebentar..."
    )
    
    try:
        success = load_chart_data_to_cache()
        
        if success:
            await processing_msg.edit_text(
                f"✅ Data chart berhasil dimuat!\n\n"
                f"📊 Total hari: {len(CHART_CACHE)} hari\n"
                f"📁 Lokasi: {CACHE_DIR}\n\n"
                f"Gunakan: /cc <kode_saham>"
            )
        else:
            await processing_msg.edit_text(
                f"❌ Gagal memuat data!\n"
                f"Pastikan folder {CACHE_DIR} berisi file txt."
            )
    except Exception as e:
        await processing_msg.edit_text(
            f"❌ Error loading cache: {str(e)}"
        )
