# boom.py
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
import logging
from imporh import*

logger = logging.getLogger(__name__)

class BoomTracker:
    def __init__(self, cache_dir="/home/ec2-user/database/cache"):
        self.cache_dir = cache_dir
        self.ram_cache = {}
        self.files_info = []
        self.last_reload = None
        
        # Load data saat inisialisasi
        self.files_info = self.get_available_files()
        logger.info(f"BoomTracker initialized. Found {len(self.files_info)} files.")
    
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
        
        files.sort(key=lambda x: x['date'], reverse=True)
        return files
    
    def load_stock_data(self, file_path):
        """Load stock data from JSON txt file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            kode_saham = data.get('kode_saham', [])
            penutupan = data.get('penutupan', [])
            volume = data.get('volume', [])
            
            stocks = []
            for i in range(1, len(kode_saham)):
                if (i < len(penutupan) and i < len(volume) and 
                    kode_saham[i] and penutupan[i] and volume[i]):
                    try:
                        stocks.append({
                            'kode': str(kode_saham[i]).strip().upper(),
                            'close': float(penutupan[i]),
                            'volume': float(volume[i])
                        })
                    except (ValueError, TypeError):
                        continue
            
            return pd.DataFrame(stocks)
            
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return pd.DataFrame()
    
    def reload_data(self, days=20):
        """Reload data 20 hari terakhir ke RAM"""
        logger.info("Reloading data to RAM cache...")
        
        self.ram_cache.clear()
        self.files_info = self.get_available_files()
        
        if not self.files_info:
            logger.warning("No data files found")
            return
        
        max_files = min(days, len(self.files_info))
        
        for i, file_info in enumerate(self.files_info[:max_files]):
            filename = file_info['filename']
            df = self.load_stock_data(file_info['path'])
            
            if not df.empty:
                self.ram_cache[filename] = df
        
        self.last_reload = datetime.now()
        logger.info(f"Loaded {len(self.ram_cache)} files to cache")
    
    def find_boom_stocks(self):
        """Find boom stocks: volume > 0.99x avg 20d, naik 0-2.5%"""
        if not self.ram_cache or len(self.files_info) < 20:
            return []
        
        recent_files = self.files_info[:20]
        
        # Data hari ini
        latest_filename = recent_files[0]['filename']
        df_today = self.ram_cache.get(latest_filename)
        
        if df_today is None or df_today.empty:
            return []
        
        # Hitung rata-rata volume 20 hari
        volume_avg_20d = {}
        
        for file_info in recent_files:
            filename = file_info['filename']
            df = self.ram_cache.get(filename)
            
            if df is None or df.empty:
                continue
            
            for _, row in df.iterrows():
                kode = row['kode']
                volume = row['volume']
                
                if kode not in volume_avg_20d:
                    volume_avg_20d[kode] = []
                
                if volume > 0:
                    volume_avg_20d[kode].append(volume)
        
        # Hitung rata-rata
        for kode in volume_avg_20d:
            if volume_avg_20d[kode]:
                volume_avg_20d[kode] = sum(volume_avg_20d[kode]) / len(volume_avg_20d[kode])
            else:
                volume_avg_20d[kode] = 0
        
        # Data kemarin
        yesterday_filename = recent_files[1]['filename']
        df_yesterday = self.ram_cache.get(yesterday_filename)
        
        if df_yesterday is None or df_yesterday.empty:
            return []
        
        # Filter saham
        results = []
        
        for _, row in df_today.iterrows():
            kode = row['kode']
            close_today = row['close']
            volume_today = row['volume']
            
            if close_today == 0 or volume_today == 0:
                continue
            
            # Cari harga kemarin
            yesterday_row = df_yesterday[df_yesterday['kode'] == kode]
            if yesterday_row.empty:
                continue
            
            close_yesterday = yesterday_row.iloc[0]['close']
            if close_yesterday == 0:
                continue
            
            # Hitung perubahan %
            chg_pct = ((close_today - close_yesterday) / close_yesterday) * 100
            
            # Filter: naik 0-2.5%
            if chg_pct < 0 or chg_pct > 2.5:
                continue
            
            # Filter volume > 0.99x avg
            avg_vol = volume_avg_20d.get(kode, 0)
            if avg_vol == 0 or volume_today < (0.99 * avg_vol):
                continue
            
            # Hitung valuasi
            valuasi = volume_today * close_today
            
            results.append({
                'kode': kode,
                'volume': volume_today,
                'close': close_today,
                'chg': chg_pct,
                'val': valuasi
            })
        
        # Sort by valuasi
        results.sort(key=lambda x: x['val'], reverse=True)
        return results[:50]

# Initialize tracker
boom_tracker = BoomTracker()

@is_authorized_user 
@spy      
@vip       
async def boom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /boom"""
    await update.message.reply_text("Mencari saham BOOM...")
    
    try:
        # Reload jika belum ada data
        if not boom_tracker.ram_cache:
            await update.message.reply_text("Loading data...")
            boom_tracker.reload_data()
        
        if len(boom_tracker.files_info) < 20:
            await update.message.reply_text(f"Data kurang dari 20 hari")
            return
        
        results = boom_tracker.find_boom_stocks()
        
        if not results:
            await update.message.reply_text("Tidak ada saham yang memenuhi kriteria")
            return
        
        # Format output
        message = "<b>SAHAM BOOM</b>\n"
        message += "Vol &gt; 0.99x avg20d, naik 0-2.5%\n\n"
        message += "<code>"
        message += f"{'Kode':<6} {'Volume':>10} {'Close':>7} {'Chg%':>6} {'Val':>8}\n"
        message += "-" * 45 + "\n"
        
        for item in results:
            vol_str = format_number(item['volume'])
            val_str = format_number(item['val'])
            
            message += f"{item['kode']:<6} {vol_str:>10} {item['close']:>7.0f} {item['chg']:>6.2f} {val_str:>8}\n"
        
        message += "</code>\n"
        message += f"\nTotal: {len(results)} saham"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error in boom_command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")

async def reload3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reload boom tracker data"""
    await update.message.reply_text("🔄 Reloading boom data...")
    
    try:
        boom_tracker.reload_data()
        
        info = {
            'files_loaded': len(boom_tracker.ram_cache),
            'total_files': len(boom_tracker.files_info),
            'last_reload': boom_tracker.last_reload.strftime("%Y-%m-%d %H:%M:%S") if boom_tracker.last_reload else "Never"
        }
        
        message = "<b>✅ Boom Data Reloaded</b>\n\n"
        message += f"Files loaded: {info['files_loaded']}\n"
        message += f"Total available: {info['total_files']}\n"
        message += f"Last reload: {info['last_reload']}"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error reloading boom data: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
def format_number(num):
    """Format ke B/M/K"""
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return f"{num:.0f}"