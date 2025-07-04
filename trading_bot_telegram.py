import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import io
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingAnalyzer:
    def __init__(self):
        self.user_data = {}  # Dictionary untuk menyimpan data per user
        self.user_cache = {}  # Dictionary untuk cache per user
        self.data_folder = r"C:\Users\nedquad12\Documents\Foreign\Trading\File"
        
    def _get_user_key(self, user_id):
        """Generate cache key for user"""
        return f"user_{user_id}"
        
    def _is_cache_valid(self, user_id, stock_code):
        """Check if cache is still valid (5 minutes)"""
        user_key = self._get_user_key(user_id)
        if user_key not in self.user_cache:
            return False
            
        cache_data = self.user_cache[user_key]
        if cache_data['stock_code'] != stock_code:
            return False
            
        # Check if 5 minutes have passed
        cache_time = cache_data['timestamp']
        current_time = datetime.now()
        time_diff = current_time - cache_time
        
        return time_diff.total_seconds() < 300  # 5 minutes = 300 seconds
        
    def load_stock_data(self, stock_code, user_id):
        """Load stock data from Excel file for specific user"""
        user_key = self._get_user_key(user_id)
        
        # Check cache first
        if self._is_cache_valid(user_id, stock_code):
            # Use cached data
            cached_data = self.user_cache[user_key]
            self.user_data[user_key] = {
                'df': cached_data['df'],
                'processed_data': cached_data['processed_data'],
                'current_stock': cached_data['stock_code']
            }
            return True, f"Data {stock_code} dimuat dari cache"
        
        try:
            file_path = os.path.join(self.data_folder, f"{stock_code}.xlsx")
            if not os.path.exists(file_path):
                file_path = os.path.join(self.data_folder, f"{stock_code}.xls")
                if not os.path.exists(file_path):
                    return False, "Kode saham tidak ditemukan di database. Beritahu admin untuk menambahkan kode saham. Kontak admin @rendanggedang atau https://x.com/saberial_link/"
            
            df = pd.read_excel(file_path)
            
            # Initialize user data if not exists
            if user_key not in self.user_data:
                self.user_data[user_key] = {}
                
            self.user_data[user_key]['df'] = df
            self.user_data[user_key]['current_stock'] = stock_code.upper()
            self.process_data(user_id)
            
            # Cache the data
            self.user_cache[user_key] = {
                'stock_code': stock_code.upper(),
                'df': df,
                'processed_data': self.user_data[user_key]['processed_data'],
                'timestamp': datetime.now()
            }
            
            return True, f"Data {stock_code} berhasil dimuat dan di-cache"
            
        except Exception as e:
            return False, f"Error loading file: {str(e)}"
    
    def process_data(self, user_id):
        """Process and prepare data for analysis for specific user"""
        user_key = self._get_user_key(user_id)
    
        if user_key not in self.user_data or self.user_data[user_key]['df'] is None:
             return
    
        df = self.user_data[user_key]['df'].copy()
        
        # Convert Time to datetime
        df['Time'] = pd.to_datetime(df['Time'], format='%H:%M:%S').dt.time
        
        # Remove commas from Price and convert to float
        if 'Price' in df.columns:
            df['Price'] = df['Price'].astype(str).str.replace(',', '').astype(float)
        
        # Create quantity categories
        def categorize_qty(qty):
            if qty <= 100:
                return 'micro'
            elif qty <= 500:
                return 'small'
            elif qty <= 3000:
                return 'medium'
            elif qty <= 15000:
                return 'big'
            else:
                return 'whale'
        
        df['Category'] = df['Qty'].apply(categorize_qty)
        
        # Create time intervals
        def get_time_bucket_10min(time_obj):
            dt = datetime.combine(datetime.today(), time_obj)
            minutes = dt.minute
            bucket_minute = (minutes // 10) * 10
            return dt.replace(minute=bucket_minute, second=0).time()

        def get_time_bucket_30min(time_obj):
            dt = datetime.combine(datetime.today(), time_obj)
            minutes = dt.minute
            bucket_minute = (minutes // 30) * 30
            return dt.replace(minute=bucket_minute, second=0).time()

        df['TimeBucket10Min'] = df['Time'].apply(get_time_bucket_10min)
        df['TimeBucket30Min'] = df['Time'].apply(get_time_bucket_30min)
        
        # Identify Buy/Sell transactions
        df['IsBuy'] = df['BT'].notna() & (df['BT'] != '') & df['BC'].notna() & (df['BC'] != '')
        df['IsSell'] = df['ST'].notna() & (df['ST'] != '') & df['SC'].notna() & (df['SC'] != '')

        # Extract broker codes
        df['BuyBrokerCode'] = df['BC'].fillna('').astype(str).str.strip()
        df['SellBrokerCode'] = df['SC'].fillna('').astype(str).str.strip()

        # Extract trader type
        df['BuyTraderType'] = df['BT'].fillna('').astype(str).str.strip()
        df['SellTraderType'] = df['ST'].fillna('').astype(str).str.strip()

        # Determine active broker code
        df['BrokerCode'] = df.apply(lambda x: 
           x['BuyBrokerCode'] if x['IsBuy'] 
           else x['SellBrokerCode'] if x['IsSell']
           else '', axis=1)

        df['TraderTypeClean'] = df.apply(lambda x:
           x['BuyTraderType'] if x['IsBuy']
           else x['SellTraderType'] if x['IsSell'] 
           else '', axis=1)
        
        # Create transaction direction
        df['Direction'] = df.apply(lambda x: 'Buy' if x['IsBuy'] else 'Sell' if x['IsSell'] else 'Unknown', axis=1)
        
        self.user_data[user_key]['processed_data'] = df

    def generate_broker_chart(self, interval='30min', category='All', user_id=None):
        """Generate broker analysis chart for specific user"""
        user_key = self._get_user_key(user_id)

        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return None, "No data loaded"

        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
        
        title = f'Top Broker Analysis - {current_stock} ({interval})'
        if category != 'All':
            title += f' ({category.title()} Category)'


    # Set time bucket based on interval
        time_bucket_col = 'TimeBucket30Min' if interval == '30min' else 'TimeBucket10Min'
        filtered_df = processed_data.copy()  # FIXED here
        filtered_df['TimeBucket'] = filtered_df[time_bucket_col]
        
        # Filter by category if specified
        if category != 'All':
            filtered_df = filtered_df[filtered_df['Category'] == category]
        
        if filtered_df.empty:
            return None, "No data to display"
        
        # Analyze buy and sell by broker code
        buy_data = filtered_df[filtered_df['IsBuy'] == True]
        sell_data = filtered_df[filtered_df['IsSell'] == True]
        
        buy_by_broker = buy_data.groupby('BuyBrokerCode')['Qty'].sum().sort_values(ascending=False)
        sell_by_broker = sell_data.groupby('SellBrokerCode')['Qty'].sum().sort_values(ascending=False)
        
        # Get top brokers
        all_brokers = set(buy_by_broker.index) | set(sell_by_broker.index)
        broker_totals = {}
        
        for broker in all_brokers:
            if broker and broker.strip() and broker != 'nan':
                buy_qty = buy_by_broker.get(broker, 0)
                sell_qty = sell_by_broker.get(broker, 0)
                broker_totals[broker] = buy_qty + sell_qty
        
        # Sort brokers by total activity and take top 15
        top_brokers = sorted(broker_totals.items(), key=lambda x: x[1], reverse=True)[:15]
        top_broker_codes = [broker[0] for broker in top_brokers]
        
        # Prepare data for plotting
        buy_quantities = [buy_by_broker.get(broker, 0) for broker in top_broker_codes]
        sell_quantities = [sell_by_broker.get(broker, 0) for broker in top_broker_codes]
        
        # Create matplotlib figure
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(14, 8))
        
        # watermark
        fig.text(0.5, 0.5, '@saberial_link',
            fontsize=60, color='gray',
            ha='center', va='center', alpha=0.5, rotation=30, weight='bold')
        
        x = np.arange(len(top_broker_codes))
        width = 0.35
        
        # Create clustered bar chart
        bars1 = ax.bar(x - width/2, buy_quantities, width, label='Buy Volume', 
                       color='#2E8B57', alpha=0.8)
        bars2 = ax.bar(x + width/2, sell_quantities, width, label='Sell Volume', 
                       color='#DC143C', alpha=0.8)
        
        # Customize chart
        ax.set_xlabel('Broker Code', fontsize=12)
        ax.set_ylabel('Quantity', fontsize=12)
    
        if category != 'All':
            title += f' ({category.title()} Category)'
        
        ax.set_title(title, fontsize=14)
        ax.set_xticks(x)
        ax.set_xticklabels(top_broker_codes, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        # Add value labels on bars
        def add_value_labels(bars, values):
            for bar, value in zip(bars, values):
                if value > 0:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + max(buy_quantities + sell_quantities)*0.01,
                           f'{value:,}', ha='center', va='bottom', fontsize=8, rotation=0)
        
        add_value_labels(bars1, buy_quantities)
        add_value_labels(bars2, sell_quantities)
        
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        
        return img_buffer, "Chart generated successfully"

    def generate_pie_chart(self, category='All', user_id=None):
        """Generate pie chart for broker distribution"""
        user_key = self._get_user_key(user_id)
    
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return None, "No data loaded"
    
        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
    
        filtered_df = processed_data.copy()
    
        # Create matplotlib figure
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # watermark
        fig.text(0.5, 0.5, '@saberial_link',
            fontsize=60, color='gray',
            ha='center', va='center', alpha=0.5, rotation=30, weight='bold')
        
        category = category
        if category == 'All':
            # Show distribution by category
            category_data = processed_data.groupby('Category')['Qty'].sum()
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57']
            
            wedges, texts, autotexts = ax.pie(category_data.values, labels=category_data.index, 
                                              autopct='%1.1f%%', startangle=90, colors=colors)
            
            ax.set_title(f'Distribution by Category - {current_stock}')
            
            # Add legend with quantities
            legend_labels = [f'{cat}: {qty:,}' for cat, qty in category_data.items()]
            ax.legend(wedges, legend_labels, title="Categories", loc="center left", 
                     bbox_to_anchor=(1, 0, 0.5, 1))
        else:
            # Show broker distribution for selected category
            filtered_df = filtered_df[filtered_df['Category'] == category]
            
            # Group by broker code
            broker_data = filtered_df.groupby('BrokerCode')['Qty'].sum().sort_values(ascending=False)
            
            # Take top 10 brokers
            if len(broker_data) > 10:
                top_brokers = broker_data.head(10)
                others_sum = broker_data.tail(len(broker_data) - 10).sum()
                if others_sum > 0:
                    top_brokers['Others'] = others_sum
                broker_data = top_brokers
            
            # Create pie chart for brokers
            colors = plt.cm.Set3(range(len(broker_data)))
            wedges, texts, autotexts = ax.pie(broker_data.values, labels=broker_data.index, 
                                              autopct='%1.1f%%', startangle=90, colors=colors)
            
            ax.set_title(f'Broker Distribution - {current_stock} ({category.title()} Category)')
            
            # Add legend with quantities
            legend_labels = [f'{broker}: {qty:,}' for broker, qty in broker_data.items()]
            ax.legend(wedges, legend_labels, title="Brokers", loc="center left", 
                     bbox_to_anchor=(1, 0, 0.5, 1))
        
        # Enhance text readability
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_weight('bold')
        
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        
        return img_buffer, "Pie chart generated successfully"

    def get_broker_details(self, broker_code, interval='30min', user_id=None):
        """Get detailed analysis for specific broker"""
        user_key = self._get_user_key(user_id)
       
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return "No data loaded"
    
        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
    
    # Set time bucket based on interval
        time_bucket_col = 'TimeBucket30Min' if interval == '30min' else 'TimeBucket10Min'
        data = processed_data.copy()
        
        # Set time bucket based on interval
        time_bucket_col = 'TimeBucket30Min' if interval == '30min' else 'TimeBucket10Min'
        data = processed_data.copy()
        data['TimeBucket'] = data[time_bucket_col]
        
        # Filter data for this broker
        broker_buy_data = data[(data['IsBuy'] == True) & (data['BuyBrokerCode'] == broker_code)]
        broker_sell_data = data[(data['IsSell'] == True) & (data['SellBrokerCode'] == broker_code)]
        
        # Format detailed analysis
        detail_text = (
             "============================\n"
             "📢 Owner: https://x.com/saberial_link/\n"
             "============================\n\n"
            f"📊 BROKER ANALYSIS: {broker_code}\n"
        )
        detail_text += f"📈 Stock: {current_stock}\n"
        detail_text += f"⏱️ Interval: {interval}\n"
        detail_text += "=" * 40 + "\n\n"
        
        # Buy Analysis
        detail_text += "🟢 BUY TRANSACTIONS:\n"
        detail_text += "-" * 30 + "\n"
        if not broker_buy_data.empty:
            buy_total = broker_buy_data['Qty'].sum()
            buy_count = len(broker_buy_data)
            buy_avg = buy_total / buy_count if buy_count > 0 else 0
            buy_avg_price = broker_buy_data['Price'].mean()
            buy_total_value = (broker_buy_data['Price'] * broker_buy_data['Qty']).sum() * 100
            
            detail_text += f"Total Buy Quantity: {buy_total:,}\n"
            detail_text += f"Number of Transactions: {buy_count:,}\n"
            detail_text += f"Average Buy Size: {buy_avg:,.0f}\n"
            detail_text += f"Average Buy Price: {buy_avg_price:,.0f}\n"
            detail_text += f"Total Buy Value: Rp {buy_total_value:,.0f}\n"
            
            # Buy by time bucket
            buy_by_time = broker_buy_data.groupby('TimeBucket').agg({
                'Qty': 'sum',
                'Price': 'mean'
            }).sort_index()
            
            buy_value_by_time = broker_buy_data.groupby('TimeBucket', group_keys=False).apply(
                lambda x: (x['Price'] * x['Qty']).sum() * 100
            ).sort_index()
            
            detail_text += "\n📊 Buy by Time:\n"
            for time_bucket, row in buy_by_time.iterrows():
                qty = row['Qty']
                avg_price = row['Price']
                value = buy_value_by_time.get(time_bucket, 0)
                detail_text += f"{str(time_bucket)}: {qty:,} @ {avg_price:,.0f} (Rp {value:,.0f})\n"
        else:
            detail_text += "No buy transactions found.\n"
        
        detail_text += "\n"
        
        # Sell Analysis
        detail_text += "🔴 SELL TRANSACTIONS:\n"
        detail_text += "-" * 30 + "\n"
        if not broker_sell_data.empty:
            sell_total = broker_sell_data['Qty'].sum()
            sell_count = len(broker_sell_data)
            sell_avg = sell_total / sell_count if sell_count > 0 else 0
            sell_avg_price = broker_sell_data['Price'].mean()
            sell_total_value = (broker_sell_data['Price'] * broker_sell_data['Qty']).sum() * 100
            
            detail_text += f"Total Sell Quantity: {sell_total:,}\n"
            detail_text += f"Number of Transactions: {sell_count:,}\n"
            detail_text += f"Average Sell Size: {sell_avg:,.0f}\n"
            detail_text += f"Average Sell Price: {sell_avg_price:,.0f}\n"
            detail_text += f"Total Sell Value: Rp {sell_total_value:,.0f}\n"
            
            # Sell by time bucket
            sell_by_time = broker_sell_data.groupby('TimeBucket').agg({
                'Qty': 'sum',
                'Price': 'mean'
            }).sort_index()
            
            sell_value_by_time = broker_sell_data.groupby('TimeBucket', group_keys=False).apply(
                lambda x: (x['Price'] * x['Qty']).sum() * 100
            ).sort_index()
            
            detail_text += "\n📊 Sell by Time:\n"
            for time_bucket, row in sell_by_time.iterrows():
                qty = row['Qty']
                avg_price = row['Price']
                value = sell_value_by_time.get(time_bucket, 0)
                detail_text += f"{str(time_bucket)}: {qty:,} @ {avg_price:,.0f} (Rp {value:,.0f})\n"
        else:
            detail_text += "No sell transactions found.\n"
        
        # Net Analysis
        buy_total = broker_buy_data['Qty'].sum() if not broker_buy_data.empty else 0
        sell_total = broker_sell_data['Qty'].sum() if not broker_sell_data.empty else 0
        net_position = buy_total - sell_total
        
        detail_text += "\n" + "=" * 40 + "\n"
        detail_text += "📊 NET POSITION SUMMARY:\n"
        detail_text += "-" * 30 + "\n"
        detail_text += f"Total Buy:  {buy_total:,}\n"
        detail_text += f"Total Sell: {sell_total:,}\n"
        detail_text += f"Net Position: {net_position:,} "
        
        if net_position > 0:
            detail_text += "(🟢 NET BUYER)\n"
        elif net_position < 0:
            detail_text += "(🔴 NET SELLER)\n"
        else:
            detail_text += "(⚪ BALANCED)\n"
        
        return detail_text

    def get_broker_list(self, user_id=None):
        """Get list of available brokers"""
        user_key = self._get_user_key(user_id)
    
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return []
    
        processed_data = self.user_data[user_key]['processed_data']
    
    # Get all unique broker codes
        buy_brokers = processed_data['BuyBrokerCode'].unique()
        sell_brokers = processed_data['SellBrokerCode'].unique()
    
        all_brokers = set()
        for broker in buy_brokers:
            if broker and broker.strip() and broker != 'nan':
               all_brokers.add(broker.strip())
        for broker in sell_brokers:
            if broker and broker.strip() and broker != 'nan':
               all_brokers.add(broker.strip())
    
        return sorted(list(all_brokers))

# Initialize analyzer
analyzer = TradingAnalyzer()

# Bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = """
🤖 Selamat datang di Broker Analys Bot!
Twitter Owner: https://x.com/saberial_link/

Perintah yang tersedia:
/start - Menampilkan pesan ini
/stock <kode> - Memuat data saham (contoh: /stock BBRI)
/broker - Analisis broker (perlu memuat data dulu)
/pie - Chart pie distribusi (perlu memuat data dulu)
/help - Bantuan

Contoh penggunaan:
1. /stock BBRI
2. /broker
3. /pie
"""
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = """
Twitter Owner: https://x.com/saberial_link/
📖 PANDUAN PENGGUNAAN:

1 Memuat Data Saham:
   /stock <kode_saham>
   Contoh: /stock BBRI

2 Analisis Broker:
   /broker - Menampilkan chart analisis broker
   
3 Chart Pie:
   /pie - Menampilkan distribusi kategori
   
4 Detail Broker:
   Setelah /broker, klik tombol broker untuk detail

📊 Interval waktu: 30 menit dan 10 menit
📈 Kategori: micro, small, medium, big, whale
"""
    await update.message.reply_text(help_text)
    
async def broker_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get broker details by user input"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    # Ganti pengecekan ini
    if user_key not in analyzer.user_data or analyzer.user_data[user_key].get('processed_data') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /stock <kode>")
        return

    if not context.args:
        await update.message.reply_text("❌ Silakan masukkan kode broker. Contoh: /detail BK")
        return

    broker_code = context.args[0].upper()
    interval = analyzer.user_data[user_key].get('last_interval', '30min')
    
    if broker_code not in analyzer.get_broker_list(user_id):  # Tambahkan user_id
        current_stock = analyzer.user_data[user_key]['current_stock']  # Ambil dari user_data
        await update.message.reply_text(f"❌ Broker {broker_code} tidak ditemukan pada data {current_stock}.")
        return

    loading_msg = await update.message.reply_text("⏳ Mengambil detail broker...")
    details = analyzer.get_broker_details(broker_code, interval, user_id)  # Tambahkan user_id

    # Split if message is too long
    if len(details) > 4096:
        chunks = [details[i:i+4096] for i in range(0, len(details), 4096)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(details)

    await loading_msg.delete()


async def load_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Load stock data"""
    if not context.args:
        await update.message.reply_text("❌ Silakan masukkan kode saham. Contoh: /stock BBRI")
        return
    
    stock_code = context.args[0].upper()
    user_id = update.effective_user.id  # Tambahkan ini
    
    loading_msg = await update.message.reply_text(f"⏳ Memuat data {stock_code}...")
    
    success, message = analyzer.load_stock_data(stock_code, user_id)  # Tambahkan user_id
    
    if success:
        await loading_msg.edit_text(f"✅ {message}!\n\nSekarang Anda dapat menggunakan:\n/broker - Analisis broker\n/pie - Chart pie - Daftar broker")
    else:
        await loading_msg.edit_text(f"❌ {message}")

async def broker_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate broker analysis"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    # Ganti pengecekan ini
    if user_key not in analyzer.user_data or analyzer.user_data[user_key].get('processed_data') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /stock <kode>")
        return
    
    # Create inline keyboard for options
    keyboard = [
        [
            InlineKeyboardButton("30 Menit - All", callback_data="broker_30min_All"),
            InlineKeyboardButton("10 Menit - All", callback_data="broker_10min_All")
        ],
        [
            InlineKeyboardButton("30 Menit - Whale", callback_data="broker_30min_whale"),
            InlineKeyboardButton("10 Menit - Whale", callback_data="broker_10min_whale")
        ],
        [
            InlineKeyboardButton("30 Menit - Big", callback_data="broker_30min_big"),
            InlineKeyboardButton("10 Menit - Big", callback_data="broker_10min_big")
        ],
        [
            InlineKeyboardButton("30 Menit - Medium", callback_data="broker_30min_medium"),
            InlineKeyboardButton("10 Menit - Medium", callback_data="broker_10min_medium")
        ],
        [
            InlineKeyboardButton("30 Menit - Small", callback_data="broker_30min_small"),
            InlineKeyboardButton("10 Menit - Small", callback_data="broker_10min_small")
        ],
        [
            InlineKeyboardButton("30 Menit - Micro", callback_data="broker_30min_micro"),
            InlineKeyboardButton("10 Menit - Micro", callback_data="broker_10min_micro")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Pilih interval dan kategori untuk analisis broker:", reply_markup=reply_markup)

async def pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate pie chart"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    # Ganti pengecekan ini
    if user_key not in analyzer.user_data or analyzer.user_data[user_key].get('processed_data') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /stock <kode>")
        return
    
    # Create inline keyboard for category selection
    keyboard = [
        [
            InlineKeyboardButton("All Categories", callback_data="pie_All"),
            InlineKeyboardButton("Whale", callback_data="pie_whale")
        ],
        [
            InlineKeyboardButton("Big", callback_data="pie_big"),
            InlineKeyboardButton("Medium", callback_data="pie_medium")
        ],
        [
            InlineKeyboardButton("Small", callback_data="pie_small"),
            InlineKeyboardButton("Micro", callback_data="pie_micro")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Pilih kategori untuk pie chart:", reply_markup=reply_markup)

async def list_brokers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available brokers"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    # Ganti pengecekan ini
    if user_key not in analyzer.user_data or analyzer.user_data[user_key].get('processed_data') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /stock <kode>")
        return
    
    brokers = analyzer.get_broker_list(user_id)  # Tambahkan user_id
    
    if brokers:
        current_stock = analyzer.user_data[user_key]['current_stock']  # Ambil dari user_data
        broker_text = f"📋 Daftar Broker {current_stock}:\n\n"
        for i, broker in enumerate(brokers, 1):
            broker_text += f"{i}. {broker}\n"
        
        broker_text += f"\n💡 Total: {len(brokers)} broker"
        await update.message.reply_text(broker_text)
    else:
        await update.message.reply_text("❌ Tidak ada broker yang ditemukan")
        
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_key = f"user_{user_id}"  # ✅ fix user_key
    data = query.data
    if data.startswith("broker_"):
        # Handle broker analysis
        parts = data.split("_")
        interval = parts[1]
        category = parts[2] 
        analyzer.user_data[user_key]['last_interval'] = interval

        
        loading_msg = await query.edit_message_text("⏳ Membuat chart analisis broker...")
        
        img_buffer, message = analyzer.generate_broker_chart(interval, category, user_id)  # Tambahkan user_id
        
        if img_buffer:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img_buffer,
                caption=f"📊 Broker Analysis - {analyzer.user_data[user_key]['current_stock']} ({interval}, {category})"
            )
            
            await context.bot.send_message(
                 chat_id=query.message.chat_id,
                 text="ℹ️ Untuk melihat detail broker, ketik:\n/detail <kode broker>\n\nContoh:\n/detail BK"
            )

            
            await loading_msg.delete()
        else:
            await loading_msg.edit_text(f"❌ {message}")
    
    elif data.startswith("pie_"):
        # Handle pie chart
        category = data.split("_")[1]
        
        loading_msg = await query.edit_message_text("⏳ Membuat pie chart...")
        
        img_buffer, message = analyzer.generate_pie_chart(category, user_id)
   
        if img_buffer:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img_buffer,
                caption=f"📊 Distribution Chart - {analyzer.user_data[user_key]['current_stock']} ({category})"

            )
            await loading_msg.delete()
        else:
            await loading_msg.edit_text(f"❌ {message}")
    
    elif data.startswith("detail_"):
        # Handle broker details
        parts = data.split("_")
        broker_code = parts[1]
        interval = parts[2]
        
        loading_msg = await query.edit_message_text("⏳ Mengambil detail broker...")
        
        details = analyzer.get_broker_details(broker_code, interval)
        
        # Split message if too long
        if len(details) > 4096:
            # Split into chunks
            chunks = [details[i:i+4096] for i in range(0, len(details), 4096)]
            for chunk in chunks:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=chunk
                )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=details
            )
        
        await loading_msg.delete()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def main():
    """Run the bot"""
    # Create the Application
    application = Application.builder().token("7616134678:AAEZkZr1oxwI0c4VW8JPrf1qvyWtf9RChrQ").build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stock", load_stock))
    application.add_handler(CommandHandler("detail", broker_detail))
    application.add_handler(CommandHandler("broker", broker_analysis)) 
    application.add_handler(CommandHandler("pie", pie_chart))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Run the bot
    print("🤖 Broker Analys Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
    