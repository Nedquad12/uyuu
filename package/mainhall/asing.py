# asing30.py
import os
import json
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

CACHE_DIR = "/home/ec2-user/database/cache"

def get_last_30_files():
    """Ambil 30 file txt terakhir berdasarkan tanggal"""
    files = []
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith('.txt'):
            try:
                # Parse tanggal dari nama file (format: DDMMYY.txt)
                date_str = filename.replace('.txt', '')
                file_date = datetime.strptime(date_str, '%d%m%y')
                file_path = os.path.join(CACHE_DIR, filename)
                files.append((file_date, file_path))
            except:
                continue
    
    # Sort berdasarkan tanggal, ambil 30 terakhir
    files.sort(reverse=True)
    return files[:30]

def calculate_foreign_net():
    """Hitung net foreign (buy - sell) untuk 30 hari"""
    files = get_last_30_files()
    
    if len(files) == 0:
        return None, 0
    
    # Dictionary untuk menyimpan total per saham
    foreign_data = {}
    
    for file_date, file_path in files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            kode_saham = data.get('kode_saham', [])
            foreign_buy = data.get('foreign_buy', [])
            foreign_sell = data.get('foreign_sell', [])
            
            # Skip header row (index 0)
            for i in range(1, len(kode_saham)):
                kode = kode_saham[i]
                
                # Validasi data
                if not kode or kode == "KODE SAHAM":
                    continue
                
                try:
                    buy = float(foreign_buy[i]) if i < len(foreign_buy) else 0
                    sell = float(foreign_sell[i]) if i < len(foreign_sell) else 0
                    net = buy - sell
                    
                    if kode not in foreign_data:
                        foreign_data[kode] = 0
                    
                    foreign_data[kode] += net
                except (ValueError, TypeError):
                    continue
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue
    
    return foreign_data, len(files)

def format_number(num):
    """Format angka dengan pemisah ribuan"""
    if num >= 0:
        return f"{int(num):,}".replace(',', '.')
    else:
        return f"{int(num):,}".replace(',', '.')

async def asing30_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /as"""
    await update.message.reply_text("⏳ Memproses data asing 30 hari terakhir...")
    
    foreign_data, days_count = calculate_foreign_net()
    
    if not foreign_data:
        await update.message.reply_text("❌ Tidak ada data yang tersedia")
        return
    
    # Filter: hanya tampilkan jika > 100k atau < -100k
    filtered_data = {k: v for k, v in foreign_data.items() 
                     if v > 100000 or v < -100000}
    
    if not filtered_data:
        await update.message.reply_text(
            f"📊 Tidak ada saham dengan akumulasi asing > 100K atau < -100K "
            f"dalam {days_count} hari terakhir"
        )
        return
    
    # Sort: positif dari terbesar, lalu negatif dari terbesar (absolut)
    positive = {k: v for k, v in filtered_data.items() if v > 0}
    negative = {k: v for k, v in filtered_data.items() if v < 0}
    
    sorted_positive = sorted(positive.items(), key=lambda x: x[1], reverse=True)
    sorted_negative = sorted(negative.items(), key=lambda x: x[1])
    
    # Gabungkan: positif dulu, baru negatif
    sorted_data = sorted_positive + sorted_negative
    
    # Split data menjadi chunks (maksimal 30 baris per pesan)
    chunk_size = 30
    chunks = [sorted_data[i:i + chunk_size] for i in range(0, len(sorted_data), chunk_size)]
    
    total_pages = len(chunks)
    
    for page_num, chunk in enumerate(chunks, 1):
        # Format output dengan HTML dan <pre> untuk monospace
        message = f"📊 <b>Akumulasi Asing {days_count} Hari</b>\n"
        message += f"<i>Halaman {page_num}/{total_pages}</i>\n\n"
        
        message += "<pre>"
        message += f"{'Kode':<6} {'Asing':>13} {'Sim':<3} {'Hari':<4}\n"
        message += "-" * 35 + "\n"
        
        for kode, net in chunk:
            symbol = "💚" if net > 0 else "❤️"
            formatted_net = format_number(net)
            message += f"{kode:<6} {formatted_net:>13} {symbol:<3} {days_count:<4}\n"
        
        message += "</pre>\n"
        
        if page_num == total_pages:
            message += f"\n<i>Total: {len(sorted_data)} saham</i>\n"
            message += f"<i>Filter: >100K atau <-100K lembar</i>"
        
        await update.message.reply_text(message, parse_mode='HTML')

async def reload7_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /reload7"""
    await update.message.reply_text("🔄 Mengulang perhitungan...")
    await asing30_command(update, context)