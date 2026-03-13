import sys
sys.path.append("/home/ec2-user/package/machine")
from flow import PriceFlowAnalyzer
from imporh import *

KHUSUS_IDS = {6208519947}

analyzer = PriceFlowAnalyzer()

@is_authorized_user
@spy
@vip
@with_queue_control 
async def load_flow_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Load flow data from multiple days"""
    user_id = update.effective_user.id

    if user_id not in KHUSUS_IDS:
        await update.message.reply_text("Silakan unggah file Excel secara langsung. Ambil data dari IPOT. Tidak paham bagaimana mengambilnya? ketik /helpvideo")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Silakan masukkan kode saham. Contoh: /flow BBRI")
        return
    
    stock_code = context.args[0].upper()
    loading_msg = await update.message.reply_text(f"⏳ Memuat data flow {stock_code}...")
    
    success, message = analyzer.load_flow_data(stock_code, user_id)
    
    if success:
        await loading_msg.edit_text(f"✅ {message}!\n\nSekarang Anda dapat menggunakan:\n/flowanalysis - Analisis price flow")
    else:
        await loading_msg.edit_text(f"⚠️ {message}")

@is_authorized_user
@spy
@vip
@with_queue_control
async def handle_file_upload_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Excel file upload for flow analysis"""
    user_id = update.effective_user.id
    message = update.message

    # Hanya proses jika ada dokumen
    if not message.document:
        await message.reply_text("⚠️ Harap kirim file Excel (.xlsx)")
        return

    file = message.document
    file_name = file.file_name.lower()

    if not (file_name.endswith('.xlsx') or file_name.endswith('.xls')):
        await message.reply_text("⚠️ Format tidak didukung. Hanya menerima Excel .xlsx/.xls")
        return

    loading_msg = await message.reply_text("⏳ Mengunduh dan memproses file...")

    try:
        file_obj = await file.get_file()
        file_path = f"/tmp/{file.file_unique_id}_{file.file_name}"
        await file_obj.download_to_drive(file_path)

        # Baca file Excel
        df = pd.read_excel(file_path)

        # Kolom wajib: Price, Qty
        needed_cols = {'Price', 'Qty'}
        missing = needed_cols - set(df.columns)
        if missing:
            await loading_msg.edit_text(f"⚠️ File kurang kolom berikut: {', '.join(missing)}")
            return

        # Proses dan simpan data
        user_key = f"user_{user_id}"
        current_stock_name = f"UPLOADED_{datetime.now().strftime('%H%M%S')}"
        
        # Initialize user data if not exists
        if user_key not in analyzer.user_data:
            analyzer.user_data[user_key] = {}
        
        # Simpan DataFrame mentah
        analyzer.user_data[user_key]['df'] = df
        analyzer.user_data[user_key]['current_stock'] = current_stock_name
        
        # Proses data untuk flow analysis
        analyzer.process_flow_data(user_id)
        
        # Hapus file temporary
        os.remove(file_path)

        await loading_msg.edit_text("✅ File berhasil diproses!\n\nSekarang Anda dapat menggunakan:\n/flowanalysis - Analisis price flow")

    except Exception as e:
        await loading_msg.edit_text(f"⚠️ Gagal memproses file:\n{str(e)}")
        # Bersihkan file jika ada error
        if os.path.exists(file_path):
            os.remove(file_path)

@is_authorized_user
@spy
@vip
@with_queue_control 
async def flow_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate price flow analysis"""
    user_id = update.effective_user.id
    user_key = f"user_{user_id}"
    
    if user_key not in analyzer.user_data or analyzer.user_data[user_key].get('processed_data') is None:
        await update.message.reply_text("⚠️ Silakan muat data flow terlebih dahulu dengan /flow <kode> atau upload file Excel dengan caption /flow")
        return
    
    # Create inline keyboard for options
    keyboard = [
        [
            InlineKeyboardButton("Top 20 Price Levels", callback_data="flow_top20"),
            InlineKeyboardButton("Top 50 Price Levels", callback_data="flow_top50")
        ],
        [
            InlineKeyboardButton("Full Analysis", callback_data="flow_full"),
            InlineKeyboardButton("Chart View", callback_data="flow_chart")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Pilih jenis analisis price flow:", reply_markup=reply_markup)

async def flow_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks for flow analysis"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_key = f"user_{user_id}"
    data = query.data
    
    if data.startswith("flow_"):
        action = data.split("_")[1]
        
        loading_msg = await query.edit_message_text("⏳ Memproses analisis price flow...")
        
        if action == "chart":
            # Generate chart
            img_buffer, message = analyzer.generate_flow_chart(user_id)
            
            if img_buffer:
                current_stock = analyzer.user_data[user_key]['current_stock']
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=img_buffer,
                    caption=f"📊 Price Flow Chart - {current_stock}"
                )
                await loading_msg.delete()
            else:
                await loading_msg.edit_text(f"⚠️ {message}")
        else:
            # Generate text analysis
            limit = 20 if action == "top20" else 50 if action == "top50" else None
            analysis_text = analyzer.get_flow_analysis(user_id, limit)
            
            if len(analysis_text) > 4096:
                # Split into chunks if too long
                chunks = [analysis_text[i:i+4096] for i in range(0, len(analysis_text), 4096)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await loading_msg.edit_text(chunk)
                    else:
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=chunk
                        )
            else:
                await loading_msg.edit_text(analysis_text)