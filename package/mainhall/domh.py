import sys
sys.path.append ("/home/ec2-user/package/machine")
from dom import TradingDomisili
from imporh import *
KHUSUS_ID = {6208519947}  # Ganti dengan user_id khusus kamu

dom_analyzer = TradingDomisili()

@is_authorized_user
@spy
@vip
@with_queue_control 
async def load_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Load DOM data"""
    user_id = update.effective_user.id

    if user_id not in KHUSUS_ID:
        await update.message.reply_text("Silakan unggah file Excel secara langsung. Ambil data dari IPOT. Tidak paham bagaimana mengambilnya? Hubungi @Rendanggedang")
        return

    if not context.args:
        await update.message.reply_text("❌ Silakan masukkan kode saham DOM. Contoh: /dom BBRI")
        return

    stock_code = context.args[0].upper()
    user_id = update.effective_user.id

    loading_msg = await update.message.reply_text(f"⏳ Memuat data DOM {stock_code}...")

    success, message = dom_analyzer.load_dom_data(stock_code, user_id)
    if success:
        await loading_msg.edit_text(f"✅ {message}!\n\nSekarang Anda dapat menggunakan:\n/domisili- Analisis domisili\n/piedom - Chart pie")
    else:
        await loading_msg.edit_text(f"❌ {message}")

@is_authorized_user
@spy
@vip
@with_queue_control
async def handle_file_upload_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Excel or text file upload from user"""
    user_id = update.effective_user.id
    message = update.message

    # Hanya proses jika ada dokumen
    if not message.document:
        await message.reply_text("❌ Harap kirim file Excel (.xlsx) atau .txt")
        return

    file = message.document
    file_name = file.file_name.lower()

    if not (file_name.endswith('.xlsx') or file_name.endswith('.xls') or file_name.endswith('.txt') or file_name.endswith('.csv')):
        await message.reply_text("❌ Format tidak didukung. Hanya menerima excel .xlsx")
        return

    loading_msg = await message.reply_text("⏳ Mengunduh dan memproses file...")

    try:
        file_obj = await file.get_file()
        file_path = f"/tmp/{file.file_unique_id}_{file.file_name}"
        await file_obj.download_to_drive(file_path)

        # Coba baca file
        if file_name.endswith(".txt") or file_name.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Kolom wajib minimal: Time, Price, BT, ST (Stock opsional)
        needed_cols = {'Time', 'Price', 'BT', 'ST'}
        missing = needed_cols - set(df.columns)
        if missing:
            await loading_msg.edit_text(f"❌ File kurang kolom berikut: {', '.join(missing)}")
            return

        # Tambahkan kolom kosong jika 'BC' dan 'SC' tidak ada
        for col in ['BC', 'SC']:
            if col not in df.columns:
                df[col] = ''

        # Jika tidak ada kolom 'Stock', buat dummy
        if 'Stock' not in df.columns:
            df['Stock'] = 'UNKNOWN'

        # Simpan data ke cache DOM
        user_key = f"dom_data{user_id}"
        current_stock_name = f"Stock_{datetime.now().strftime('%H%M%S')}"
        
        dom_analyzer.dom_data[user_key] = {
            'df': df,
            'current_stock_dom': current_stock_name,
           'last_interval': '30min'
          }

            # Wajib proses data biar kolom Category, TimeBucket, dll muncul
        dom_analyzer.process_dom_data(user_id)

        
        # Hapus file temporary
        os.remove(file_path)

        await loading_msg.edit_text("✅ File berhasil diproses!\n\nSekarang Anda dapat menggunakan:\n/domisili - Analisis domisili\n/piedom - Chart pie")

    except Exception as e:
        await loading_msg.edit_text(f"❌ Gagal memproses file:\n{str(e)}")
        
@is_authorized_user
@spy
@vip
@with_queue_control 
async def domisili_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get broker details by user input"""
    user_id = update.effective_user.id
    user_key = f"dom_data{user_id}"
    
    if user_key not in dom_analyzer.dom_data or dom_analyzer.dom_data[user_key].get('processed_dom') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /dom <kode> atau kirim file Excel")
        return

    if not context.args:
        await update.message.reply_text("❌ Silakan masukkan kode broker. Contoh: /detaildom F")
        return
    
    broker_code = context.args[0].upper()
    interval = dom_analyzer.dom_data[user_key].get('last_interval', '30min')
    
    if broker_code not in dom_analyzer.get_broker_list(user_id):  # Tambahkan user_id
        current_stock = dom_analyzer.dom_data[user_key]['current_stock_dom']  # Ambil dari dom_data
        await update.message.reply_text(f"❌ Broker {broker_code} tidak ditemukan pada data {current_stock}.")
        return

    loading_msg = await update.message.reply_text("⏳ Mengambil detail domisli...")
    details = dom_analyzer.get_broker_details(broker_code, interval, user_id)  # Tambahkan user_id

    # Split if message is too long
    if len(details) > 4096:
        chunks = [details[i:i+4096] for i in range(0, len(details), 4096)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(details)

    await loading_msg.delete()

@is_authorized_user
@spy
@vip
@with_queue_control 
async def domisili_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate broker analysis"""
    user_id = update.effective_user.id
    user_key = f"dom_data{user_id}"
    
    # Ganti pengecekan ini
    if user_key not in dom_analyzer.dom_data or dom_analyzer.dom_data[user_key].get('processed_dom') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /dom <kode> atau kirim file Excel")
        return
    
    # Create inline keyboard for options
    keyboard = [
        [
            InlineKeyboardButton("30 Menit - All", callback_data="dom_broker_30min_All"),
            InlineKeyboardButton("10 Menit - All", callback_data="dom_broker_10min_All")
        ],
        [
            InlineKeyboardButton("30 Menit - Whale", callback_data="dom_broker_30min_whale"),
            InlineKeyboardButton("10 Menit - Whale", callback_data="dom_broker_10min_whale")
        ],
        [
            InlineKeyboardButton("30 Menit - Big", callback_data="dom_broker_30min_big"),
            InlineKeyboardButton("10 Menit - Big", callback_data="dom_broker_10min_big")
        ],
        [
            InlineKeyboardButton("30 Menit - Medium", callback_data="dom_broker_30min_medium"),
            InlineKeyboardButton("10 Menit - Medium", callback_data="dom_broker_10min_medium")
        ],
        [
            InlineKeyboardButton("30 Menit - Small", callback_data="dom_broker_30min_small"),
            InlineKeyboardButton("10 Menit - Small", callback_data="dom_broker_10min_small")
        ],
        [
            InlineKeyboardButton("30 Menit - Micro", callback_data="dom_broker_30min_micro"),
            InlineKeyboardButton("10 Menit - Micro", callback_data="dom_broker_10min_micro")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Pilih interval dan kategori untuk analisis broker:", reply_markup=reply_markup)

@is_authorized_user
@spy
@with_queue_control 
async def pie_chart_dom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate pie chart"""
    user_id = update.effective_user.id
    user_key = f"dom_data{user_id}"
    
    if user_key not in dom_analyzer.dom_data or dom_analyzer.dom_data[user_key].get('processed_dom') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /dom <kode> atau kirim file Excel")
        return
    
    # Create inline keyboard for category selection
    keyboard = [
        [
            InlineKeyboardButton("All Categories", callback_data="dom_pie_All"),
            InlineKeyboardButton("Whale", callback_data="dom_pie_whale")
        ],
        [
            InlineKeyboardButton("Big", callback_data="dom_pie_big"),
            InlineKeyboardButton("Medium", callback_data="dom_pie_medium")
        ],
        [
            InlineKeyboardButton("Small", callback_data="dom_pie_small"),
            InlineKeyboardButton("Micro", callback_data="dom_pie_micro")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Pilih kategori untuk pie chart:", reply_markup=reply_markup)

@is_authorized_user
@spy
@with_queue_control 
async def list_domisili(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available brokers"""
    user_id = update.effective_user.id
    user_key = f"dom_data{user_id}"
    
    if user_key not in dom_analyzer.dom_data or dom_analyzer.dom_data[user_key].get('processed_dom') is None:
        await update.message.reply_text("❌ Silakan muat data saham terlebih dahulu dengan /dom <kode> atau kirim file Excel")
        return
    
    brokers = dom_analyzer.get_broker_list(user_id)  # Tambahkan user_id
    
    if brokers:
        current_stock = dom_analyzer.dom_data[user_key]['current_stock_dom']  # Ambil dari dom_data
        broker_text = f"📋 Daftar Domisili {current_stock}:\n\n"
        for i, broker in enumerate(brokers, 1):
            broker_text += f"{i}. {broker}\n"
        
        broker_text += f"\n💡 Total: {len(brokers)} Domisili"
        await update.message.reply_text(broker_text)
    else:
        await update.message.reply_text("❌ Tidak ada broker yang ditemukan")
        
async def button_callbackdom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_key = f"dom_data{user_id}"  # ✅ fix user_key
    data = query.data
    if data.startswith("dom_broker_"):
        # Handle broker analysis
        parts = data.split("_")
        interval = parts[2]
        category = parts[3] 
        dom_analyzer.dom_data[user_key]['last_interval'] = interval

        
        loading_msg = await query.edit_message_text("⏳ Membuat chart analisis domisili...")
        
        img_buffer, message = dom_analyzer.generate_dom_chart(interval, category, user_id)  # Tambahkan user_id
        
        if img_buffer:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img_buffer,
                caption=f"📊 Domisili Analysis - {dom_analyzer.dom_data[user_key]['current_stock_dom']} ({interval}, {category})"
            )
            
            await context.bot.send_message(
                 chat_id=query.message.chat_id,
                 text="ℹ️ Untuk melihat detail domisili, ketik:\n/detaildom <domisili>\n\nContoh:\n/detaildom F"
            )

            
            await loading_msg.delete()
        else:
            await loading_msg.edit_text(f"❌ {message}")
    
    elif data.startswith("dom_pie_"):
        # Handle pie chart
        category = data.split("_")[2]
        
        loading_msg = await query.edit_message_text("⏳ Membuat pie chart...")
        
        img_buffer, message = dom_analyzer.generate_pie_chart(category, user_id)
   
        if img_buffer:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=img_buffer,
                caption=f"📊 Distribution Chart - {dom_analyzer.dom_data[user_key]['current_stock_dom']} ({category})"

            )
            await loading_msg.delete()
        else:
            await loading_msg.edit_text(f"❌ {message}")
    
    elif data.startswith("dom_detail_"):
        # Handle broker details
        parts = data.split("_")
        broker_code = parts[1]
        interval = parts[2]
        
        loading_msg = await query.edit_message_text("⏳ Mengambil detail domisili...")
        
        details = dom_analyzer.get_broker_details(broker_code, interval)
        
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
