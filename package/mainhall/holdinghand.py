import sys
sys.path.append("/home/ec2-user/package/machine")
from utama import TelegramStockDataViewer
from imporh import *
import json
from datetime import datetime
import os
import glob
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

viewer = TelegramStockDataViewer()

# ============================================
# CACHE SYSTEM - RAM-based JSON cache
# ============================================
class DataCache:
    def __init__(self):
        self.cache = None
        self.last_loaded = None
        
    def load_from_excel(self):
        """Load data from Excel files and cache in RAM as JSON"""
        try:
            folder_path = "/home/ec2-user/database/data"
            excel_files = sorted(glob.glob(os.path.join(folder_path, "*.xlsx")), reverse=True)
            
            if not excel_files:
                logger.warning("No Excel files found in database/data")
                return None
            
            all_data = []
            
            for file_path in excel_files:
                try:
                    df = pd.read_excel(file_path)
                    
                    # Map columns by position (A=0, B=1, etc.)
                    column_mapping = {
                        0: 'Date',           # A
                        1: 'Code',           # B
                        5: 'Local IS',       # F
                        6: 'Local CP',       # G
                        7: 'Local PF',       # H
                        8: 'Local IB',       # I
                        9: 'Local ID',       # J
                        10: 'Local MF',      # K
                        11: 'Local SC',      # L
                        12: 'Local FD',      # M
                        13: 'Local OT',      # N
                        14: 'Total Local',   # O
                        15: 'Foreign IS',    # P
                        16: 'Foreign CP',    # Q
                        17: 'Foreign PF',    # R
                        18: 'Foreign IB',    # S
                        19: 'Foreign ID',    # T
                        20: 'Foreign MF',    # U
                        21: 'Foreign SC',    # V
                        22: 'Foreign FD',    # W
                        23: 'Foreign OT',    # X
                        24: 'Total Foreign'  # Y
                    }
                    
                    # Select and rename columns
                    selected_cols = list(column_mapping.keys())
                    df_selected = df.iloc[:, selected_cols].copy()
                    df_selected.columns = list(column_mapping.values())
                    
                    # Convert Date to datetime and extract month-year
                    df_selected['Date'] = pd.to_datetime(df_selected['Date'], errors='coerce')
                    df_selected['Month'] = df_selected['Date'].dt.strftime('%Y-%m')
                    
                    # Convert to dict records
                    records = df_selected.to_dict('records')
                    
                    # Convert datetime objects to string for JSON serialization
                    for record in records:
                        if isinstance(record.get('Date'), pd.Timestamp):
                            record['Date'] = record['Date'].isoformat()
                    
                    all_data.extend(records)
                    
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    continue
            
            if all_data:
                self.cache = all_data
                self.last_loaded = datetime.now().isoformat()
                logger.info(f"Cache loaded: {len(all_data)} records from {len(excel_files)} files")
                return True
            
            return None
            
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return None
    
    def get_cache(self):
        """Get cached data"""
        if self.cache is None:
            self.load_from_excel()
        return self.cache
    
    def search_stock(self, code):
        """Search stock data from cache"""
        if self.cache is None:
            return None
        
        results = []
        for record in self.cache:
            val = record.get('Code', '')
            if isinstance(val, str) and val.upper() == code.upper():
                results.append(record)
        return results
    
    def get_stats(self):
        """Get cache statistics"""
        if self.cache is None:
            return "Cache is empty"
        
        return f"📊 Cache Stats:\n" \
               f"• Records: {len(self.cache)}\n" \
               f"• Last loaded: {self.last_loaded}\n" \
               f"• Memory size: ~{sys.getsizeof(json.dumps(self.cache)) / 1024:.2f} KB"

# Initialize cache
data_cache = DataCache()

# ============================================
# RELOAD COMMAND
# ============================================
@is_authorized_user
@spy
async def reload7_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reload cache from Excel files"""
    try:
        await update.message.reply_text("🔄 Reloading cache from Excel files...")
        
        result = data_cache.load_from_excel()
        
        if result:
            stats = data_cache.get_stats()
            await update.message.reply_text(f"✅ Cache reloaded successfully!\n\n{stats}")
        else:
            await update.message.reply_text("❌ Failed to reload cache. Check logs for details.")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error reloading cache: {str(e)}")
        logger.error(f"Error in reload_cache_command: {e}")

# ============================================
# MODIFIED FUNCTIONS TO USE CACHE
# ============================================
@is_authorized_user
@spy
@with_queue_control 
@with_rate_limit
async def create_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Load from cache instead of Excel
    cache_data = data_cache.get_cache()
    if cache_data is None:
        await update.message.reply_text("❌ Tidak ada data. Gunakan /reload7 untuk memuat data.")
        return

    # Convert cache to DataFrame for compatibility with existing code
    viewer.combined_df = pd.DataFrame(cache_data)
    
    if viewer.combined_df is None or viewer.combined_df.empty:
        await update.message.reply_text("❌ Tidak ada data. API bermasalah, segera beritahu admin @Rendanggedang atau https://x.com/saberial_link/.")
        return

    parts = update.message.text.split()
    code = parts[1].upper() if len(parts) > 1 else None

    # 📝 Bangun tombol pilihan field
    field_buttons = []
    for field in viewer.plot_fields:
        label = viewer.button_labels.get(field, field)
        callback_data = f"field_{field.replace(' ', '_')}"
        field_buttons.append(InlineKeyboardButton(label, callback_data=callback_data))

    # 📳 Susun tombol 2 kolom per baris
    keyboard = []
    for i in range(0, len(field_buttons), 2):
        keyboard.append(field_buttons[i:i + 2])

    # ➕ Tambahkan tombol tambahan
    keyboard.append([
        InlineKeyboardButton("Total Local", callback_data="field_Total_Local"),
        InlineKeyboardButton("Total Foreign", callback_data="field_Total_Foreign")
    ])
    keyboard.append([
        InlineKeyboardButton("Select All", callback_data="select_all"),
        InlineKeyboardButton("Clear All", callback_data="clear_all")
    ])
    keyboard.append([
        InlineKeyboardButton("Generate Chart", callback_data=f"generate_chart_{code if code else 'all'}")
    ])

    markup = InlineKeyboardMarkup(keyboard)

    chart_text = "📊 Pilih data yang diinginkan\nJika sudah jangan lupa klik Generate Chart\n"
    if code:
        chart_text += f"Stock: {code}\n"
    chart_text += "\nSelect fields to include in the chart:"

    await update.message.reply_text(chart_text, reply_markup=markup)

@is_authorized_user
@spy
@with_queue_control  
@with_rate_limit   
async def handle_chart_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    user_data = viewer.get_user_data(user_id)

    await query.answer()

    if data.startswith('field_'):
        field = data[6:].replace('_', ' ')
        if field in user_data['chart_selections']:
            user_data['chart_selections'].remove(field)
        else:
            user_data['chart_selections'].add(field)

    elif data == 'select_all':
        user_data['chart_selections'] = set(viewer.plot_fields + ['Total Local', 'Total Foreign'])

    elif data == 'clear_all':
        user_data['chart_selections'] = set()

    elif data.startswith('generate_chart_'):
        code = data[15:] if data[15:] != 'all' else None

        if not user_data['chart_selections']:
            await query.answer("❌ Pilih salah satu!", show_alert=True)
            return

        try:
            # Load from cache
            cache_data = data_cache.get_cache()
            if cache_data:
                viewer.combined_df = pd.DataFrame(cache_data)
            
            selected_fields = list(user_data['chart_selections'])
            chart_buffer = viewer.create_line_chart(selected_fields, code)
            if chart_buffer is None:
                await query.answer("❌ Tidak ada data dalam kriteria ini!", show_alert=True)
                return

            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=chart_buffer,
                caption=f"📈 Line Chart{' for ' + code if code else ''}"
            )

            viewer.combined_df = None
            chart_buffer.close()
            plt.close('all')
            gc.collect()
            
            await query.edit_message_reply_markup(reply_markup=None)

            await query.edit_message_text(
                text="✅ Chart berhasil dibuat.",
                reply_markup=None
            )

            await query.answer("✅ Chart sukses!")

        except Exception as e:
            await query.answer(f"❌ Error membuat chart: {str(e)}", show_alert=True)
        return

    # Update pilihan yang sedang dipilih
    selected_text = ", ".join(sorted(user_data['chart_selections'])) if user_data['chart_selections'] else "None"
    updated_text = f"📊 Chart Configuration\n\nSelected fields: {selected_text}\n\nSelect fields to include in the chart:"

    await query.edit_message_text(
        text=updated_text,
        reply_markup=query.message.reply_markup
    )
   
@is_authorized_user    
@spy     
@with_queue_control 
@with_rate_limit
async def search_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Masukan kode saham.\nContoh: `/search BBCA`", parse_mode='Markdown')
        return
    
    code = parts[1].upper()
    
    # Search from cache
    stock_data = data_cache.search_stock(code)
    
    if stock_data is None or len(stock_data) == 0:
        await update.message.reply_text(f"❌ Tidak ada data untuk saham {code}.")
        return

    # Convert to DataFrame for formatting
    stock_df = pd.DataFrame(stock_data)
    response_text = viewer.format_stock_data(stock_df)
    await update.message.reply_text(response_text)

@is_authorized_user 
@spy   
@with_queue_control 
@with_rate_limit
async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer.load_watchlist_data()
     
    if viewer.watchlist_data is None:
        await update.message.reply_text("❌ Tidak ada data. API bermasalah, segera beritahu admin @Rendanggedang atau https://x.com/saberial_link/.")
        return
    
    # Create keyboard for market cap filter
    keyboard = [
       [
          InlineKeyboardButton("🔥 High Cap (≥20T)", callback_data="wl_high"),
          InlineKeyboardButton("📈 Mid Cap (≥1T)", callback_data="wl_mid"),
        ],
       [
           InlineKeyboardButton("📊 Low Cap (≥80M)", callback_data="wl_low"),
           InlineKeyboardButton("📉 Micro Cap (<80M)", callback_data="wl_micro"),
       ],
       [
           InlineKeyboardButton("📋 All Caps", callback_data="wl_all"),
       ]
     ]

    markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Pilih kategori:", reply_markup=markup)
    
async def handle_watchlist_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        call = update.callback_query
        await call.answer()

        parts = call.data.split('_', 3)
        cap_filter = parts[2]
        page_str = parts[3]
        page = int(page_str)

        filter_param = None if cap_filter == 'all' else cap_filter
        stocks = viewer.get_watchlist_stocks(filter_param)
        response = viewer.format_watchlist_response(stocks, filter_param)

        # Bagi jadi beberapa halaman (misal setiap 4000 karakter)
        page_size = 4000
        pages = [response[i:i + page_size] for i in range(0, len(response), page_size)]

        if page >= len(pages):
            await context.bot.send_message(chat_id=call.message.chat_id, text="❌ Halaman tidak ditemukan.")
            return

        # Buat tombol prev/next
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"wl_page_{cap_filter}_{page - 1}"))
        if page < len(pages) - 1:
            buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"wl_page_{cap_filter}_{page + 1}"))

        markup = InlineKeyboardMarkup([buttons]) if buttons else None

        await context.bot.edit_message_text(
            text=pages[page],
            chat_id=call.message.chat_id,
            message_id=call.message.message_id,
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error in pagination: {e}")
        try:
            await update.callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)
        except:
            pass

async def handle_watchlist_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cap_filter = query.data[3:]
    user_id = query.from_user.id

    try:
        await query.answer("🔍 Menganalisa watchlist...")

        filter_param = None if cap_filter == 'all' else cap_filter
        stocks = viewer.get_watchlist_stocks(filter_param)
        response = viewer.format_watchlist_response(stocks, filter_param)

        page_size = 4000
        pages = [response[i:i + page_size] for i in range(0, len(response), page_size)]

        if not pages:
            await context.bot.send_message(chat_id=query.message.chat.id, text="❌ Tidak ada data.")
            return

        await context.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)

        msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=pages[0],
            parse_mode='Markdown'
        )

        if len(pages) > 1:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Next (2)", callback_data=f"wl_page_{cap_filter}_1")]
            ])
            await context.bot.edit_message_reply_markup(
                chat_id=msg.chat.id,
                message_id=msg.message_id,
                reply_markup=markup
            )

    except Exception as e:
        await query.answer(f"❌ Error: {str(e)}", show_alert=True)
        logger.error(f"Error in handle_watchlist_filter: {e}")

@is_authorized_user
@spy
@with_queue_control 
@with_rate_limit
async def holdings_summary_with_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Load from cache
        cache_data = data_cache.get_cache()
        if cache_data is None:
            await update.message.reply_text("❌ Tidak ada data Shareholder untuk emiten ini. Gunakan /reload7 untuk memuat data.")
            return

        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Masukan kode saham.\nContoh: `/hol BBCA`", parse_mode='Markdown')
            return

        code = parts[1].upper()
        
        # Search from cache
        stock_data = data_cache.search_stock(code)
        if not stock_data:
            await update.message.reply_text(f"❌ Tidak ada data untuk saham {code}.")
            return
        
        df = pd.DataFrame(stock_data)

        # Load harga penutupan dari folder foreign
        folder_path = "/home/ec2-user/database/foreign"
        excel_files = sorted(glob.glob(os.path.join(folder_path, "*.xlsx")), reverse=True)
        if not excel_files:
            await update.message.reply_text("❌ Tidak ada file harga penutupan di folder foreign.")
            return

        harga_data = pd.read_excel(excel_files[0])
        harga_dict = dict(zip(harga_data['Kode Saham'].str.upper(), harga_data['Penutupan']))

        closing_price = harga_dict.get(code)
        if closing_price is None:
            await update.message.reply_text(f"❌ Tidak ditemukan harga penutupan untuk {code}.")
            return

        # Parse Month from cache (already in YYYY-MM format)
        df['Month_Period'] = pd.to_datetime(df['Month'], format='%Y-%m').dt.to_period('M')
        response = f"📊 Holding Summary for {code}\n💰 Harga Penutupan: Rp {await format_rupiah(closing_price)}\n"

        previous_totals = {}

        for month, group in df.groupby('Month_Period'):
            totals = {
                'Ritel': group[['Local ID', 'Foreign ID']].sum().sum() * closing_price,
                'Bandar Lokal': group[['Local IS', 'Local MF', 'Local SC', 'Local OT']].sum().sum() * closing_price,
                'Bandar Asing': group[['Foreign IS', 'Foreign MF', 'Foreign SC', 'Foreign OT']].sum().sum() * closing_price,
                'Big Investor Lokal': group[['Local CP', 'Local PF', 'Local IB', 'Local FD']].sum().sum() * closing_price,
                'Big Investor Asing': group[['Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign FD']].sum().sum() * closing_price,
            }

            response += f"\n📅 {month.strftime('%b %Y')}\n"

            for category, total in totals.items():
                prev_total = previous_totals.get(category, total)
                change_pct = ((total - prev_total) / prev_total * 100) if prev_total != 0 else 0
                arrow = "🟩" if change_pct > 0 else "🟥" if change_pct < 0 else "⚪"
                response += f"{arrow} {category}: Rp {await format_rupiah(total)} ({change_pct:+.1f}%)\n"

            response += "─" * 30 + "\n"
            previous_totals = totals

        await update.message.reply_text(response)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Error in holdings_summary: {e}")

    finally:
        viewer.combined_df = None
        import gc
        gc.collect()
        
async def format_rupiah(value):
    """Format angka ke Rupiah dengan T/B/M/K"""
    if value >= 1e12:
        return f"{value / 1e12:.2f}T"
    elif value >= 1e9:
        return f"{value / 1e9:.2f}B"
    elif value >= 1e6:
        return f"{value / 1e6:.2f}M"
    elif value >= 1e3:
        return f"{value / 1e3:.2f}K"
    else:
        return f"{value:,.0f}"

# ============================================
# FAST HOLDINGS ANALYSIS USING CACHE
# ============================================
async def get_holdings_summary_fast(stock_code):
    """Get holdings summary using cache - FAST VERSION"""
    try:
        # Get data from cache (DIRECTLY from RAM, no reload)
        cache_data = data_cache.get_cache()
        
        if cache_data is None:
            return None, "Cache kosong. Gunakan /reload7 untuk memuat data."
        
        # Filter untuk stock_code dari cache yang sudah ada
        stock_data = [
            record for record in cache_data 
            if isinstance(record.get('Code'), str) and record.get('Code', '').upper() == stock_code.upper()
        ]
        
        if not stock_data or len(stock_data) == 0:
            return None, f"Tidak ada data kepemilikan untuk {stock_code}"
        
        # Convert to DataFrame
        df = pd.DataFrame(stock_data)
        
        # Load harga penutupan dari folder foreign
        folder_path = "/home/ec2-user/database/foreign"
        excel_files = sorted(glob.glob(os.path.join(folder_path, "*.xlsx")), reverse=True)
        
        if not excel_files:
            return None, "Tidak ada file harga penutupan"
        
        harga_data = pd.read_excel(excel_files[0])
        harga_dict = dict(zip(harga_data['Kode Saham'].str.upper(), harga_data['Penutupan']))
        
        closing_price = harga_dict.get(stock_code)
        if closing_price is None:
            return None, f"Tidak ditemukan harga penutupan untuk {stock_code}"
        
        # Parse Month from cache (already in YYYY-MM format)
        df['Month_Period'] = pd.to_datetime(df['Month'], format='%Y-%m').dt.to_period('M')
        
        holdings_message = f"```\n👥 HOLDINGS SUMMARY - {stock_code}\n"
        holdings_message += f"💰 Harga Penutupan: Rp {await format_rupiah(closing_price)}\n"
        holdings_message += "="*45 + "\n"
        
        previous_totals = {}
        
        for month, group in df.groupby('Month_Period'):
            totals = {
                'Ritel': group[['Local ID', 'Foreign ID']].sum().sum() * closing_price,
                'Bandar Lokal': group[['Local IS', 'Local MF', 'Local SC', 'Local OT']].sum().sum() * closing_price,
                'Bandar Asing': group[['Foreign IS', 'Foreign MF', 'Foreign SC', 'Foreign OT']].sum().sum() * closing_price,
                'Big Investor Lokal': group[['Local CP', 'Local PF', 'Local IB', 'Local FD']].sum().sum() * closing_price,
                'Big Investor Asing': group[['Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign FD']].sum().sum() * closing_price,
            }
            
            holdings_message += f"\n📅 {month.strftime('%b %Y')}\n"
            
            for category, total in totals.items():
                prev_total = previous_totals.get(category, total)
                change_pct = ((total - prev_total) / prev_total * 100) if prev_total != 0 else 0
                arrow = "🟩" if change_pct > 0 else "🟥" if change_pct < 0 else "⚪"
                holdings_message += f"{arrow} {category}: Rp {await format_rupiah(total)} ({change_pct:+.1f}%)\n"
            
            holdings_message += "─" * 30 + "\n"
            previous_totals = totals
        
        holdings_message += "```"
        
        return holdings_message, None
        
    except Exception as e:
        logger.error(f"Error in get_holdings_summary_fast: {e}")
        return None, f"Error saat menganalisis kepemilikan: {str(e)}"