import sys
sys.path.append ("/home/ec2-user/package/machine")
from order import TradingAnalyzer
from imporh import *

KHUSUS_IDS = {6208519947}

analyzer = TradingAnalyzer()

@is_authorized_user
@spy
@vip
@with_queue_control 
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

@is_authorized_user
@spy
@vip
@with_queue_control 
async def load_combined_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Load combined stock data from multiple days"""
    
    if not context.args:
        await update.message.reply_text("❌ Silakan masukkan kode saham. Contoh: /sa BBRI")
        return
    
    stock_code = context.args[0].upper()
    user_id = update.effective_user.id
    
    loading_msg = await update.message.reply_text(f"⏳ Memuat data gabungan {stock_code} (maksimal 10 hari)...")
    
    success, message = analyzer.load_combined_stock_data(stock_code, user_id)
    
    if success:
        await loading_msg.edit_text(f"✅ {message}!\n\nSekarang Anda dapat menggunakan:\n/broker - Analisis broker\n/pie - Chart pie")
    else:
        await loading_msg.edit_text(f"❌ {message}")
  
@is_authorized_user
@spy
@vip
@with_queue_control
async def handle_file_upload_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Excel or text file upload from user for order analysis"""
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

        # Kolom wajib minimal: Time, Price, Qty, BT, ST
        needed_cols = {'Time', 'Price', 'Qty', 'BT', 'ST'}  # ✅ Tambahkan 'Qty'
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

        # ✅ PERBAIKAN: Simpan data dengan benar dan panggil process_data()
        user_key = f"user_{user_id}"
        current_stock_name = f"UPLOADED_{datetime.now().strftime('%H%M%S')}"
        
        # Initialize user data if not exists
        if user_key not in analyzer.user_data:
            analyzer.user_data[user_key] = {}
        
        # Simpan DataFrame mentah
        analyzer.user_data[user_key]['df'] = df
        analyzer.user_data[user_key]['current_stock'] = current_stock_name
        
        # ✅ KUNCI: Panggil process_data untuk membuat kolom yang dibutuhkan
        analyzer.process_data(user_id)
        
        # Set default interval
        analyzer.user_data[user_key]['last_interval'] = '30min'
        
        # Cache the data (opsional)
        analyzer.user_cache[user_key] = {
            'stock_code': current_stock_name,
            'df': df,
            'processed_data': analyzer.user_data[user_key]['processed_data'],
            'timestamp': datetime.now()
        }
        
        # Hapus file temporary
        os.remove(file_path)

        await loading_msg.edit_text("✅ File berhasil diproses!\n\nSekarang Anda dapat menggunakan:\n/broker - Analisis broker\n/pie - Chart pie")

    except Exception as e:
        await loading_msg.edit_text(f"❌ Gagal memproses file:\n{str(e)}")
        # Bersihkan file jika ada error
        if os.path.exists(file_path):
            os.remove(file_path)

@is_authorized_user
@spy
@vip      
@with_queue_control 
async def load_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Load stock data"""
    user_id = update.effective_user.id

    if user_id not in KHUSUS_IDS:
        await update.message.reply_text("Silakan unggah file Excel secara langsung. Ambil data dari IPOT. Tidak paham bagaimana mengambilnya? ketik /helpvideo")
        return

    if not context.args:
        await update.message.reply_text("❌ Silakan masukkan kode saham. Contoh: /stock BBRI")
        return
    
    stock_code = context.args[0].upper()
    user_id = update.effective_user.id
    
    loading_msg = await update.message.reply_text(f"⏳ Memuat data {stock_code}...")
    
    success, message = analyzer.load_stock_data(stock_code, user_id)  # Tambahkan user_id
    if success:
        await loading_msg.edit_text(f"✅ {message}!\n\nSekarang Anda dapat menggunakan:\n/broker - Analisis broker\n/pie - Chart pie - Daftar broker")
    else:
        await loading_msg.edit_text(f"❌ {message}")

@is_authorized_user
@spy
@vip
@with_queue_control 
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

@is_authorized_user
@spy
@with_queue_control 
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

@is_authorized_user
@spy
@with_queue_control 
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
