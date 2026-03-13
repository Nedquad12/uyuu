import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from imporh import *

CACHE_DIR = "/home/ec2-user/database/cache"

# Cache di RAM untuk net asing
NET_ASING_CACHE = {
    '1d': {},   # {kode: net_value}
    '1w': {},
    '1m': {},
    '1q': {}
}

LAST_RELOAD_TIME = None

def parse_date_from_filename(filename: str) -> datetime:
    """
    Parse tanggal dari nama file format ddmmyy.txt
    Contoh: 020525.txt -> 2025-05-02
    """
    try:
        date_str = filename.replace('.txt', '')
        day = int(date_str[0:2])
        month = int(date_str[2:4])
        year = int('20' + date_str[4:6])
        return datetime(year, month, day)
    except Exception as e:
        print(f"[FALL] Error parsing date from {filename}: {e}")
        return None

def get_cache_files_in_range(start_date: datetime, end_date: datetime) -> List[str]:
    """
    Ambil semua file cache dalam rentang tanggal
    """
    if not os.path.exists(CACHE_DIR):
        print(f"[FALL] Cache directory tidak ditemukan: {CACHE_DIR}")
        return []
    
    files = []
    for filename in os.listdir(CACHE_DIR):
        if not filename.endswith('.txt'):
            continue
        
        file_date = parse_date_from_filename(filename)
        if file_date:
            print(f"[FALL] File: {filename} -> Date: {file_date.strftime('%Y-%m-%d')}")
            if start_date.date() <= file_date.date() <= end_date.date():
               files.append(os.path.join(CACHE_DIR, filename))
        else:
            print(f"[FALL] Gagal parse: {filename}")
    
    print(f"[FALL] Found {len(files)} files in range {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    return sorted(files)

def load_cache_file(file_path: str) -> Dict:
    """
    Load data dari file cache JSON
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[FALL] Error loading {file_path}: {e}")
        return None

def calculate_net_asing(data: Dict) -> Dict[str, float]:
    """
    Hitung net asing per kode saham dari satu file
    net = foreign_buy - foreign_sell
    """
    net_dict = {}
    
    try:
        kode_saham_list = data.get('kode_saham', [])
        foreign_buy_list = data.get('foreign_buy', [])
        foreign_sell_list = data.get('foreign_sell', [])
        
        # Skip header row (index 0)
        for i in range(1, len(kode_saham_list)):
            kode = kode_saham_list[i]
            
            # Ambil nilai foreign buy dan sell
            try:
                buy = float(foreign_buy_list[i]) if i < len(foreign_buy_list) else 0
                sell = float(foreign_sell_list[i]) if i < len(foreign_sell_list) else 0
                net = buy - sell
                
                if kode and isinstance(kode, str):
                    net_dict[kode] = net
            except (ValueError, TypeError, IndexError):
                continue
                
    except Exception as e:
        print(f"[FALL] Error calculating net: {e}")
    
    return net_dict

def aggregate_net_asing(file_paths: List[str]) -> Dict[str, float]:
    """
    Aggregate net asing dari multiple files
    """
    total_net = {}
    
    print(f"[FALL] Aggregating {len(file_paths)} files...")
    
    for file_path in file_paths:
        data = load_cache_file(file_path)
        if not data:
            print(f"[FALL] Failed to load: {file_path}")
            continue
        
        net_dict = calculate_net_asing(data)
        print(f"[FALL] {os.path.basename(file_path)}: {len(net_dict)} saham")
        
        # Aggregate
        for kode, net in net_dict.items():
            if kode in total_net:
                total_net[kode] += net
            else:
                total_net[kode] = net
    
    print(f"[FALL] Total aggregate: {len(total_net)} saham")
    return total_net

@is_authorized_user
@spy
@with_queue_control  
@with_rate_limit   
async def reload9_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command /reload9 - Reload cache net asing untuk semua timeframe
    """
    global LAST_RELOAD_TIME
    
    # Await the reply_text
    msg = await update.message.reply_text("🔄 Memuat cache net asing...")
    
    today = datetime.now()
    
    try:
        # 1D - hari ini saja
        files_1d = get_cache_files_in_range(today, today)
        NET_ASING_CACHE['1d'] = aggregate_net_asing(files_1d)
        
        # 1W - 7 hari terakhir
        week_ago = today - timedelta(days=7)
        files_1w = get_cache_files_in_range(week_ago, today)
        NET_ASING_CACHE['1w'] = aggregate_net_asing(files_1w)
        
        # 1M - 30 hari terakhir
        month_ago = today - timedelta(days=30)
        files_1m = get_cache_files_in_range(month_ago, today)
        NET_ASING_CACHE['1m'] = aggregate_net_asing(files_1m)
        
        # 1Q - 90 hari terakhir (quarter)
        quarter_ago = today - timedelta(days=90)
        files_1q = get_cache_files_in_range(quarter_ago, today)
        NET_ASING_CACHE['1q'] = aggregate_net_asing(files_1q)
        
        LAST_RELOAD_TIME = datetime.now()
        
        summary = (
            f"✅ Cache net asing berhasil dimuat!\n\n"
            f"📊 Summary:\n"
            f"• 1D: {len(files_1d)} file, {len(NET_ASING_CACHE['1d'])} saham\n"
            f"• 1W: {len(files_1w)} file, {len(NET_ASING_CACHE['1w'])} saham\n"
            f"• 1M: {len(files_1m)} file, {len(NET_ASING_CACHE['1m'])} saham\n"
            f"• 1Q: {len(files_1q)} file, {len(NET_ASING_CACHE['1q'])} saham\n\n"
            f"⏰ Waktu reload: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M:%S')}"
        )
        
        # Await the edit_text as well
        await msg.edit_text(summary)
        
    except Exception as e:
        # Await the edit_text in error handling too
        await msg.edit_text(f"❌ Error reload cache: {str(e)}\n\nTraceback: {repr(e)}")

@is_authorized_user
@spy
@with_queue_control  
@with_rate_limit   
async def fall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command /fall - Tampilkan pilihan timeframe
    """
    keyboard = [
        [
            InlineKeyboardButton("1D (Hari Ini)", callback_data="fall_1d"),
            InlineKeyboardButton("1W (Minggu)", callback_data="fall_1w")
        ],
        [
            InlineKeyboardButton("1M (Bulan)", callback_data="fall_1m"),
            InlineKeyboardButton("1Q (Quarter)", callback_data="fall_1q")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if LAST_RELOAD_TIME:
        reload_info = f"\n⏰ Cache terakhir: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M')}"
    else:
        reload_info = "\n⚠️ Cache belum dimuat. Gunakan /reload9"
    
    await update.message.reply_text(
        f"📊 *Analisis Net Asing*\n\n"
        f"Pilih timeframe untuk melihat:\n"
        f"• Top 20 Net Asing Terbesar (Akumulasi)\n"
        f"• Top 20 Net Asing Terkecil (Dibuang){reload_info}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def format_number(num: float) -> str:
    """Format angka dengan separator dan suffix"""
    if abs(num) >= 1_000_000_000:
        return f"{num/1_000_000_000:.2f}B"
    elif abs(num) >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif abs(num) >= 1_000:
        return f"{num/1_000:.2f}K"
    else:
        return f"{num:.0f}"

def get_top_bottom_net(timeframe: str) -> Tuple[List[Tuple], List[Tuple]]:
    """
    Ambil top 20 terbesar dan 20 terkecil (paling minus)
    Returns: (top_20_list, bottom_20_list)
    """
    net_dict = NET_ASING_CACHE.get(timeframe, {})
    
    if not net_dict:
        return [], []
    
    # Sort descending untuk top (terbesar)
    sorted_items = sorted(net_dict.items(), key=lambda x: x[1], reverse=True)
    top_20 = sorted_items[:20]
    
    # Sort ascending untuk bottom (terkecil/paling minus)
    bottom_20 = sorted(net_dict.items(), key=lambda x: x[1])[:20]
    
    return top_20, bottom_20

async def fall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback dari button timeframe
    """
    query = update.callback_query
    await query.answer()
    
    timeframe = query.data.replace('fall_', '')
    
    if not NET_ASING_CACHE.get(timeframe):
        await query.edit_message_text(
            "⚠️ Hubungi admin!\n"
            "error."
        )
        return
    
    top_20, bottom_20 = get_top_bottom_net(timeframe)
    
    if not top_20 and not bottom_20:
        await query.edit_message_text(
            f"❌ Tidak ada data untuk timeframe {timeframe.upper()}"
        )
        return
    
    # Format timeframe display
    tf_display = {
        '1d': '1D (Hari Ini)',
        '1w': '1W (Minggu)',
        '1m': '1M (Bulan)',
        '1q': '1Q (Quarter)'
    }
    
    # Build message
    message = f"📊 *Net Asing - {tf_display.get(timeframe, timeframe.upper())}*\n\n"
    
    # Top 20 (Akumulasi)
    message += "🟢 *TOP 20 AKUMULASI (Terbesar dalam lembar saham)*\n"
    message += "```\n"
    message += f"{'No':<3} {'Kode':<6} {'Net Asing':>15} {'TF':>4}\n"
    message += "-" * 33 + "\n"
    
    for idx, (kode, net) in enumerate(top_20, 1):
        message += f"{idx:<3} {kode:<6} {format_number(net):>15} {timeframe.upper():>4}\n"
    
    message += "```\n\n"
    
    # Bottom 20 (Dibuang/Minus)
    message += "🔴 *TOP 20 DIBUANG (Terminus dalam lembar saham)*\n"
    message += "```\n"
    message += f"{'No':<3} {'Kode':<6} {'Net Asing':>15} {'TF':>4}\n"
    message += "-" * 33 + "\n"
    
    for idx, (kode, net) in enumerate(bottom_20, 1):
        message += f"{idx:<3} {kode:<6} {format_number(net):>15} {timeframe.upper():>4}\n"
    
    message += "```"
    
    # Add back button
    keyboard = [[InlineKeyboardButton("« Kembali", callback_data="fall_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def fall_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol kembali"""
    query = update.callback_query
    await query.answer()
    
    # Tampilkan lagi menu timeframe
    keyboard = [
        [
            InlineKeyboardButton("1D (Hari Ini)", callback_data="fall_1d"),
            InlineKeyboardButton("1W (Minggu)", callback_data="fall_1w")
        ],
        [
            InlineKeyboardButton("1M (Bulan)", callback_data="fall_1m"),
            InlineKeyboardButton("1Q (Quarter)", callback_data="fall_1q")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if LAST_RELOAD_TIME:
        reload_info = f"\n⏰ Cache terakhir: {LAST_RELOAD_TIME.strftime('%d/%m/%Y %H:%M')}"
    else:
        reload_info = "\n⚠️ Cache belum dimuat. Gunakan /reload9"
    
    await query.edit_message_text(
        f"📊 *Analisis Net Asing*\n\n"
        f"Pilih timeframe untuk melihat:\n"
        f"• Top 20 Net Asing Terbesar (Akumulasi)\n"
        f"• Top 20 Net Asing Terkecil (Dibuang){reload_info}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
