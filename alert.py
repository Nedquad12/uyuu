import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import pandas as pd
import yfinance as yf
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pytz
import numpy as np
import json
import os
from collections import defaultdict
from functools import wraps

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class StockVolumeMonitor:
    def __init__(self, bot_token: str, admin_ids: List[int] = None):
        self.bot_token = bot_token
        self.bot = Bot(token=bot_token)
        self.application = Application.builder().token(bot_token).build()
        
        # Admin and whitelist configuration
        self.admin_ids: Set[int] = set(admin_ids) if admin_ids else set()
        
        # Timezone Indonesia
        self.tz = pytz.timezone('Asia/Jakarta')
        
        # Data storage
        self.monitored_groups: List[str] = []
        self.stock_data: Dict[str, Dict] = {}
        self.volume_history: Dict[str, List] = defaultdict(list)
        
        # Trading hours (WIB)
        self.trading_start = 9  # 09:00
        self.trading_end = 16   # 16:00
        
        # Alert settings
        self.volume_threshold = 2.0  # 2x lipat
        self.monitoring_interval = 60  # 1 menit
        self.avg_window_minutes = 120  # 2 jam untuk hitung rata-rata
        
        # Daftar saham populer Indonesia
        self.popular_stocks = [
                             
        ]
        
        self.indices = {
            'ES=F': 'USA',
            '^AXJO': 'Australia', 
            '^N225': 'Jepang',
            '^KS11': 'Korea',
            '^HSI': 'Hong Kong',
            '^TWII': 'Taiwan',
            '^KLSE': 'Malaysia',
            '^JKSE': 'Indonesia',
            '^STI': 'Singapura'
        }
        
        self.currencies = {
            'IDR=X': 'USD/IDR',
            'CNY=X': 'USD/CNY', 
            'JPY=X': 'USD/JPY',
            'EURUSD=X': 'EUR/USD',
            'GBPUSD=X': 'GBP/USD'
        }
        
        # Index trading hours (WIB)
        self.index_trading_start = 7   # 07:00
        self.index_trading_end = 16    # 16:05
        self.index_monitoring_interval = 900  # 15 menit
        
        # Index monitoring task
        self.index_monitoring_task = None
        self.index_monitored_groups: List[str] = []
        self.setup_handlers()
        
    def whitelist_required(func):
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id

        # Admins always allowed
            if user_id in self.admin_ids:
                return await func(self, update, context)

        # Groups always allowed
            if chat_id < 0:
                return await func(self, update, context)

        # Allow non-whitelist users for /start and /status
            command = update.message.text.split()[0]
            if command in ["/start", "/status"]:
                return await func(self, update, context)

        # Check if user is in hardcoded whitelist
            if user_id in WHITELIST_IDS:
                return await func(self, update, context)
   
            await update.message.reply_text(
                "❌ Anda tidak memiliki akses untuk perintah ini.\n"
                "Hubungi admin untuk mendapatkan akses."
            )
        return wrapper
 
    def admin_only(func):
        """Decorator to restrict command to admins only"""
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            if user_id not in self.admin_ids:
                await update.message.reply_text("❌ Perintah ini hanya untuk admin!")
                return
            return await func(self, update, context)
        return wrapper
    
    def whitelist_required(func):
        """Decorator to check whitelist before executing command"""
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            
            # Always allow admins
            if user_id in self.admin_ids:
                return await func(self, update, context)
            
            # Check if user or group is whitelisted
            if user_id in self.whitelisted_users or chat_id in self.whitelisted_groups:
                return await func(self, update, context)
            
            await update.message.reply_text(
                "❌ Anda tidak memiliki akses untuk menggunakan bot ini.\n"
                "Hubungi admin untuk mendapatkan akses."
            )
            return
        return wrapper
    
    def is_index_trading_hours(self) -> bool:
        """Check if current time is within index trading hours"""
        now = datetime.now(self.tz)
        return self.index_trading_start <= now.hour < self.index_trading_end or \
               (now.hour == self.index_trading_end and now.minute <= 5)


    def get_index_data(self, symbol: str) -> Optional[Dict]:
        """Get index/currency data"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Get 2 days data to calculate change
            data = ticker.history(period="2d", interval="1d")
            
            if len(data) < 2:
                return None
            
            current = data.iloc[-1]
            previous = data.iloc[-2]
            
            change = current['Close'] - previous['Close']
            change_percent = (change / previous['Close']) * 100
            
            return {
                'symbol': symbol,
                'current_price': current['Close'],
                'previous_price': previous['Close'],
                'change': change,
                'change_percent': change_percent,
                'timestamp': data.index[-1]
            }
        except Exception as e:
            logger.error(f"Error getting index data for {symbol}: {e}")
            return None
        
    def format_index_output(self, indices_data: Dict, currencies_data: Dict) -> str:
        """Format index and currency data for output"""
        now = datetime.now(self.tz)
        
        message = f"📊 *Data Indeks & Mata Uang*\n"
        message += f"⏰ {now.strftime('%H:%M WIB')} | Data tertunda 10 menit\n\n"
        
        # Indices
        message += "*📈 Indeks:*\n"
        for symbol, country in self.indices.items():
            if symbol in indices_data:
                data = indices_data[symbol]
                price = data['current_price']
                change_pct = data['change_percent']
                
                # Format price based on typical values
                if price > 1000:
                    price_str = f"{price:,.0f}"
                else:
                    price_str = f"{price:,.2f}"
                
                # Format change with + or - sign
                if change_pct >= 0:
                    change_str = f"+{change_pct:.2f}%"
                    emoji = "🟢"
                else:
                    change_str = f"{change_pct:.2f}%"
                    emoji = "🔴"
                
                message += f"{emoji} {country}: {price_str} {change_str}\n"
            else:
                message += f"⚪ {country}: Data tidak tersedia\n"
        
        # Currencies
        message += "\n*💱 Mata Uang:*\n"
        for symbol, pair in self.currencies.items():
            if symbol in currencies_data:
                data = currencies_data[symbol]
                price = data['current_price']
                change_pct = data['change_percent']
                
                # Format currency price
                if 'IDR' in pair:
                    price_str = f"{price:,.0f}"
                else:
                    price_str = f"{price:.4f}"
                
                # Format change with + or - sign
                if change_pct >= 0:
                    change_str = f"+{change_pct:.2f}%"
                    emoji = "🟢"
                else:
                    change_str = f"{change_pct:.2f}%"
                    emoji = "🔴"
                
                message += f"{emoji} {pair}: {price_str} {change_str}\n"
            else:
                message += f"⚪ {pair}: Data tidak tersedia\n"
        
        return message
    
    def setup_handlers(self):
        """Setup command handlers"""
        # Basic commands (with whitelist check)
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("add_stock", self.add_stock_command))
        self.application.add_handler(CommandHandler("remove_stock", self.remove_stock_command))
        self.application.add_handler(CommandHandler("list_stocks", self.list_stocks_command))
        self.application.add_handler(CommandHandler("index", self.index_command))
        self.application.add_handler(CommandHandler("stop_index", self.stop_index_command))
        self.application.add_handler(CommandHandler("admin_help", self.admin_help_command))
    
    @whitelist_required
    async def start_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.monitored_groups:
            self.monitored_groups.append(chat_id)
            await update.message.reply_text(
                "🚀 Bot Volume Alert Saham Indonesia telah diaktifkan!\n\n"
                "Bot akan memantau volume saham Indonesia (.JK) secara real-time "
                "dan mengirim alert ketika ada volume signifikan.\n\n"
                "Gunakan /help untuk melihat perintah yang tersedia."
            )
        else:
            await update.message.reply_text("Bot sudah aktif di grup ini!")
            
    
    @whitelist_required
    async def help_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        is_admin = user_id in self.admin_ids
        
        help_text = """
📊 *Bot Volume Alert Saham Indonesia*

*Perintah yang tersedia:*
• /start - Aktifkan bot di grup
• /status - Cek status monitoring
• /add_stock [KODE] - Tambah saham untuk dipantau
• /remove_stock [KODE] - Hapus saham dari monitoring
• /list_stocks - Lihat daftar saham yang dipantau

*Contoh penggunaan:*
• /add_stock BBRI.JK
• /remove_stock BBRI.JK

*Fitur:*
• Monitoring real-time volume saham Indonesia
• Alert otomatis ketika volume melonjak 2x lipat
• Hanya aktif saat jam trading (09:00-16:00 WIB)
• Broadcast ke semua grup yang diikuti bot
        """
        
        if is_admin:
            help_text += "\n\n🔧 *Perintah Admin:*\n"
            help_text += "• /admin_help - Bantuan khusus admin\n"
            help_text += "• /index - Lihat data indeks & mata uang + mulai monitoring\n"
            help_text += "• /stop_index - Hentikan monitoring indeks untuk grup ini"
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def admin_help_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin_help command"""
        user_id = update.effective_user.id
        if user_id not in self.admin_ids:
            await update.message.reply_text("❌ Perintah ini hanya untuk admin!")
            return
        
        admin_help_text = """
🔧 *Perintah Admin - Whitelist Management*

*Manajemen User:*
• /whitelist_add_user [USER_ID] - Tambah user ke whitelist
• /whitelist_remove_user [USER_ID] - Hapus user dari whitelist

*Manajemen Group:*
• /whitelist_add_group [GROUP_ID] - Tambah group ke whitelist
• /whitelist_remove_group [GROUP_ID] - Hapus group dari whitelist

*Kontrol Sistem:*
• /whitelist_enable - Aktifkan sistem whitelist
• /whitelist_disable - Nonaktifkan sistem whitelist
• /whitelist_status - Cek status whitelist
• /whitelist_list - Lihat daftar whitelist

*Contoh penggunaan:*
• /whitelist_add_user 123456789
• /whitelist_add_group -1001234567890
• /whitelist_remove_user 123456789

*Tips:*
• Untuk mendapatkan USER_ID, minta user mengirim pesan ke bot
• Untuk GROUP_ID, gunakan bot di grup dan lihat log
• Admin selalu memiliki akses penuh
        """
        
        await update.message.reply_text(admin_help_text, parse_mode='Markdown')
    
    
    @whitelist_required
    async def status_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        now = datetime.now(self.tz)
        is_trading_hours = self.trading_start <= now.hour < self.trading_end
        
        status_text = f"""
📈 *Status Bot Volume Alert*

⏰ Waktu: {now.strftime('%H:%M:%S WIB')}
📊 Jam Trading: {'✅ Aktif' if is_trading_hours else '❌ Tutup'}
🔍 Saham Dipantau: {len(self.popular_stocks)}
📢 Grup Terdaftar: {len(self.monitored_groups)}
🎯 Threshold Alert: {self.volume_threshold}x lipat
        """
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    @whitelist_required
    async def add_stock_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_stock command"""
        if not context.args:
            await update.message.reply_text("Gunakan: /add_stock [KODE_SAHAM]\nContoh: /add_stock BBRI.JK")
            return
        
        stock_code = context.args[0].upper()
        if not stock_code.endswith('.JK'):
            stock_code += '.JK'
        
        if stock_code not in self.popular_stocks:
            self.popular_stocks.append(stock_code)
            await update.message.reply_text(f"✅ Saham {stock_code} berhasil ditambahkan ke monitoring!")
        else:
            await update.message.reply_text(f"⚠️ Saham {stock_code} sudah ada dalam monitoring!")
    
    @whitelist_required
    async def remove_stock_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove_stock command"""
        if not context.args:
            await update.message.reply_text("Gunakan: /remove_stock [KODE_SAHAM]\nContoh: /remove_stock BBRI.JK")
            return
        
        stock_code = context.args[0].upper()
        if not stock_code.endswith('.JK'):
            stock_code += '.JK'
        
        if stock_code in self.popular_stocks:
            self.popular_stocks.remove(stock_code)
            await update.message.reply_text(f"✅ Saham {stock_code} berhasil dihapus dari monitoring!")
        else:
            await update.message.reply_text(f"⚠️ Saham {stock_code} tidak ditemukan dalam monitoring!")
    
    @whitelist_required
    async def list_stocks_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_stocks command"""
        if not self.popular_stocks:
            await update.message.reply_text("Tidak ada saham yang dipantau saat ini.")
            return
        
        stocks_text = "📊 *Daftar Saham yang Dipantau:*\n\n"
        for i, stock in enumerate(self.popular_stocks, 1):
            stocks_text += f"{i}. {stock}\n"
        
        await update.message.reply_text(stocks_text, parse_mode='Markdown')
    
    def is_trading_hours(self) -> bool:
        """Check if current time is within trading hours"""
        now = datetime.now(self.tz)
        return self.trading_start <= now.hour < self.trading_end
    
    def get_stock_data(self, symbol: str) -> Optional[Dict]:
        """Get real-time stock data"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Get intraday data (1 minute intervals)
            data = ticker.history(period="1d", interval="1m")
            
            if data.empty:
                return None
            
            # Get latest data
            latest = data.iloc[-1]
            
            return {
                'symbol': symbol,
                'price': latest['Close'],
                'volume': latest['Volume'],
                'timestamp': data.index[-1],
                'high': latest['High'],
                'low': latest['Low'],
                'open': latest['Open']
            }
        except Exception as e:
            logger.error(f"Error getting data for {symbol}: {e}")
            return None
        
    @admin_only
    async def index_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /index command (admin only)"""
        chat_id = update.effective_chat.id
        
        # Auto-add grup ke index_monitored_groups jika belum ada
        if chat_id not in self.index_monitored_groups:
            self.index_monitored_groups.append(chat_id)
            logger.info(f"Auto-added group {chat_id} to index monitored groups")
        
        await update.message.reply_text("📊 Mengambil data indeks dan mata uang...")
        
        # Get all indices data
        indices_data = {}
        for symbol in self.indices.keys():
            data = self.get_index_data(symbol)
            if data:
                indices_data[symbol] = data
        
        # Get all currencies data
        currencies_data = {}
        for symbol in self.currencies.keys():
            data = self.get_index_data(symbol)
            if data:
                currencies_data[symbol] = data
        
        # Format and send message
        message = self.format_index_output(indices_data, currencies_data)
        await update.message.reply_text(message, parse_mode='Markdown')

    @admin_only
    async def stop_index_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """Stop index monitoring for this group"""
        chat_id = update.effective_chat.id
        
        if chat_id in self.index_monitored_groups:
            self.index_monitored_groups.remove(chat_id)
            await update.message.reply_text("❌ Monitoring indeks dihentikan untuk grup ini.")
        else:
            await update.message.reply_text("⚠️ Grup ini tidak dalam daftar monitoring indeks.")

    async def monitor_indices(self):
        """Monitor indices every 15 minutes during trading hours"""
        while True:
            try:
                if not self.is_index_trading_hours():
                    logger.info("Outside index trading hours, sleeping...")
                    await asyncio.sleep(1800)  # 30 menit saat tutup
                    continue
                
                # Skip jika belum ada grup yang menggunakan /index
                if not self.index_monitored_groups:
                    logger.info("No groups registered for index monitoring, sleeping...")
                    await asyncio.sleep(300)  # 5 menit
                    continue
                
                logger.info("Monitoring indices and currencies...")
                
                # Get all indices data
                indices_data = {}
                for symbol in self.indices.keys():
                    data = self.get_index_data(symbol)
                    if data:
                        indices_data[symbol] = data
                
                # Get all currencies data
                currencies_data = {}
                for symbol in self.currencies.keys():
                    data = self.get_index_data(symbol)
                    if data:
                        currencies_data[symbol] = data
                
                # Format message
                message = self.format_index_output(indices_data, currencies_data)
                
                # Send HANYA ke grup yang sudah pakai /index
                for group_id in self.index_monitored_groups:
                    try:
                        await self.bot.send_message(
                            chat_id=group_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error sending index update to {group_id}: {e}")
                
                await asyncio.sleep(self.index_monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in index monitoring loop: {e}")
                await asyncio.sleep(300)  # 5 menit jika error
    
    def calculate_average_volume(self, symbol: str) -> float:
        """Calculate average volume for the specified time window"""
        if symbol not in self.volume_history:
            return 0
        
        history = self.volume_history[symbol]
        if len(history) < 2:
            return 0
        
        # Get volumes from last 2 hours
        cutoff_time = datetime.now(self.tz) - timedelta(minutes=self.avg_window_minutes)
        recent_volumes = [
            vol for timestamp, vol in history 
            if timestamp >= cutoff_time
        ]
        
        if not recent_volumes:
            return 0
        
        return np.mean(recent_volumes)
    
    def should_alert(self, symbol: str, current_volume: float) -> bool:
        """Check if we should send an alert"""
    
        avg_volume = self.calculate_average_volume(symbol)
        
        if avg_volume == 0:
            return False
        
        volume_ratio = current_volume / avg_volume
        return volume_ratio >= self.volume_threshold
    
    async def send_volume_alert(self, symbol: str, data: Dict, volume_ratio: float):
        """Send volume alert to all monitored groups"""
        now = datetime.now(self.tz)
        
        # Format pesan alert
        stock_name = symbol.replace('.JK', '')
        message = f"""
🚨 *VOLUME ALERT* 🚨

📊 {stock_name}
📈 Kenaikan volume {volume_ratio:.1f}x lipat pada jam {now.strftime('%H:%M')} WIB
💰 Last Price: {data['price']:,.0f}
📊 Volume: {data['volume']:,.0f}
🕐 Timestamp: {now.strftime('%d/%m/%Y %H:%M:%S')}

#VolumeAlert #{stock_name}
        """
        
        # Kirim ke semua grup yang terdaftar
        for group_id in self.monitored_groups:
            try:
                await self.bot.send_message(
                    chat_id=group_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error sending alert to {group_id}: {e}")
    
    async def monitor_stocks(self):
        """Main monitoring loop"""
        while True:
            try:
                if not self.is_trading_hours():
                    logger.info("Outside trading hours, sleeping...")
                    await asyncio.sleep(300)  # 5 menit saat tutup
                    continue
                
                logger.info(f"Monitoring {len(self.popular_stocks)} stocks...")
                
                for symbol in self.popular_stocks:
                    try:
                        data = self.get_stock_data(symbol)
                        
                        if data is None:
                            continue
                        
                        # Store volume history
                        current_time = datetime.now(self.tz)
                        self.volume_history[symbol].append((current_time, data['volume']))
                        
                        # Keep only recent history (last 4 hours)
                        cutoff_time = current_time - timedelta(hours=4)
                        self.volume_history[symbol] = [
                            (ts, vol) for ts, vol in self.volume_history[symbol]
                            if ts >= cutoff_time
                        ]
                        
                        # Check if we should alert
                        if data['volume'] >= 100000 and self.should_alert(symbol, data['volume']):
                           avg_volume = self.calculate_average_volume(symbol)
                           volume_ratio = data['volume'] / avg_volume
    
                           logger.info(f"Volume alert for {symbol}: {volume_ratio:.1f}x")
                           await self.send_volume_alert(symbol, data, volume_ratio)
                        
                        # Store latest data
                        self.stock_data[symbol] = data
                        
                    except Exception as e:
                        logger.error(f"Error monitoring {symbol}: {e}")
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def run(self):
        """Run the bot"""
        # Start the bot
        await self.application.initialize()
        await self.application.start()
        
        # Jalankan KEDUA monitoring: volume stocks DAN indices
        monitor_task = asyncio.create_task(self.monitor_stocks())
        index_monitor_task = asyncio.create_task(self.monitor_indices())
        
        # Start polling
        await self.application.updater.start_polling()
        
        logger.info("Bot started successfully! (Both stock volume and index monitoring)")
        
        try:
            await asyncio.gather(monitor_task, index_monitor_task)
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
        finally:
            await self.application.stop()

# Configuration
BOT_TOKEN = "7833221115:AAF9v8eVPM7x3rmuHF5ErSYivEnOwnk1t1c"  # Ganti dengan token bot Telegram Anda
ADMIN_IDS = [6208519947, 5751902978]  # Ganti dengan Telegram user ID admin
WHITELIST_IDS = [6208519947, 5751902978]  # ID user yang boleh akses penuh


async def main():
    """Main function"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Harap masukkan token bot Telegram Anda!")
        print("1. Buat bot baru di @BotFather")
        print("2. Dapatkan token dan ganti BOT_TOKEN di kode")
        print("3. Dapatkan user ID admin dan masukkan ke ADMIN_IDS")
        return
    
    if not ADMIN_IDS or ADMIN_IDS == [123456789, 987654321]:
        print("❌ Harap masukkan user ID admin di ADMIN_IDS!")
        print("Cara mendapatkan user ID:")
        print("1. Chat ke @userinfobot")
        print("2. Masukkan user ID ke dalam list ADMIN_IDS")
        return
    
    bot = StockVolumeMonitor(BOT_TOKEN, ADMIN_IDS)
    await bot.run()

if __name__ == "__main__":
    # Install required packages
    print("🚀 Starting Telegram Stock Volume Monitor Bot...")
    print("📊 Monitoring Indonesian stocks (.JK) for volume alerts...")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
 