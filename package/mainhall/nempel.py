from imporh import *

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_file_date_from_name(filename):
    """Extract date from filename format ddmmyy.xlsx"""
    try:
        # Remove .xlsx extension
        date_str = filename.replace('.xlsx', '').replace('.xls', '')
        if len(date_str) == 6:
            day = int(date_str[:2])
            month = int(date_str[2:4])
            year = 2000 + int(date_str[4:6])  # Convert yy to yyyy
            return datetime(year, month, day)
    except ValueError as e:
        logger.warning(f"Cannot parse date from filename {filename}: {e}")
    return None

def get_excel_files(directory):
    """Get all excel files and sort by date"""
    files = []
    for filename in os.listdir(directory):
        if filename.endswith(('.xlsx', '.xls')):
            file_date = get_file_date_from_name(filename)
            if file_date:
                files.append({
                    'filename': filename,
                    'date': file_date,
                    'path': os.path.join(directory, filename)
                })
    
    # Sort by date (newest first)
    files.sort(key=lambda x: x['date'], reverse=True)
    return files

def read_excel_data(file_path):
    """Read excel data and extract required columns"""
    try:
        # Read excel without header
        df = pd.read_excel(file_path, header=None)
        
        # Extract required columns (0-indexed)
        # B=1 (Kode Saham), K=10 (Penutupan)
        if df.shape[1] >= 11:  # Ensure we have enough columns
            data = {
                'kode_saham': df.iloc[:, 1],      # Column B
                'penutupan': df.iloc[:, 10],      # Column K
            }
            
            # Create dataframe and clean data
            result_df = pd.DataFrame(data)
            
            # Remove rows with empty kode_saham
            result_df = result_df.dropna(subset=['kode_saham'])
            
            # Convert numeric columns, replace NaN with 0
            result_df['penutupan'] = pd.to_numeric(result_df['penutupan'], errors='coerce').fillna(0)
            
            # Remove rows with 0 price
            result_df = result_df[result_df['penutupan'] > 0]
            
            return result_df
        else:
            logger.error(f"File {file_path} doesn't have enough columns")
            return None
            
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return None

def calculate_moving_averages(prices, periods):
    """Calculate moving averages for given periods"""
    mas = {}
    for period in periods:
        if len(prices) >= period:
            mas[period] = sum(prices[:period]) / period
        else:
            return None
    return mas

def check_ma_distance(ma_values, max_percent):
    """Check if distance between consecutive MAs is within max_percent"""
    periods = [3, 5, 10, 20]
    
    for i in range(len(periods) - 1):
        current_period = periods[i]
        next_period = periods[i + 1]
        
        current_ma = ma_values[current_period]
        next_ma = ma_values[next_period]
        
        # Calculate percentage difference
        if current_ma > 0:
            distance = abs(next_ma - current_ma) / current_ma
            if distance > max_percent:
                return False
    
    return True

def calculate_nempel_analysis(max_percent):
    """Main function to calculate nempel analysis"""
    directory = "/home/ec2-user/database/wl"
    
    try:
        # Get all excel files (limit to 30 files)
        excel_files = get_excel_files(directory)
        
        if len(excel_files) < 20:
            return None, "Tidak cukup data untuk analisis (minimal 20 file untuk MA20)"
        
        # Take maximum 30 files
        excel_files = excel_files[:30]
        logger.info(f"Processing {len(excel_files)} files for nempel analysis")
        
        # Collect all data organized by stock code
        data_by_stock = {}  # {kode: [day0_price, day1_price, ...]}
        
        # Process each file
        for i, file_info in enumerate(excel_files):
            logger.info(f"Processing {file_info['filename']} ({i+1}/{len(excel_files)})")
            
            df = read_excel_data(file_info['path'])
            if df is None:
                continue
            
            # Store data for each stock
            for _, row in df.iterrows():
                kode = row['kode_saham']
                price = row['penutupan']
                
                if kode not in data_by_stock:
                    data_by_stock[kode] = []
                
                data_by_stock[kode].append(price)
        
        if not data_by_stock:
            return None, "Tidak ada data yang berhasil diproses"
        
        # Calculate MA and filter stocks
        nempel_results = []
        periods = [3, 5, 10, 20]
        
        for kode, prices in data_by_stock.items():
            if len(prices) >= 20:  # Need at least 20 days for MA20
                # Calculate moving averages
                ma_values = calculate_moving_averages(prices, periods)
                
                if ma_values and check_ma_distance(ma_values, max_percent):
                    nempel_results.append({
                        'kode': kode,
                        'ma3': ma_values[3],
                        'ma20': ma_values[20]
                    })
        
        # Sort by stock code
        nempel_results.sort(key=lambda x: x['kode'])
        
        return nempel_results, None
        
    except Exception as e:
        logger.error(f"Error in calculate_nempel_analysis: {e}")
        return None, "Fitur sedang dalam perbaikan"

def format_nempel_message(nempel_data, total_files, command_type, page=1, items_per_page=20):
    """Format nempel results into message with pagination"""
    if not nempel_data:
        threshold = "5%" if command_type == "nempel" else "3%"
        return f"Tidak ada saham yang memenuhi kriteria MA nempel (jarak ≤{threshold})", None
    
    title = "NEMPEL ANALYSIS" if command_type == "nempel" else "SUPER NEMPEL ANALYSIS"
    threshold = "5%" if command_type == "nempel" else "3%"
    
    # Calculate pagination
    total_items = len(nempel_data)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    
    # Get data for current page
    page_data = nempel_data[start_idx:end_idx]
    
    message = f"```\n📊 {title}\n"
    message += f"Data: {total_files} hari | Jarak MA ≤{threshold} | Total: {total_items} saham\n"
    message += f"Halaman {page}/{total_pages} ({start_idx + 1}-{end_idx})\n"
    message += "=" * 40 + "\n"
    message += f"{'Kode':<10} {'MA3':<12} {'MA20':<12}\n"
    message += "=" * 40 + "\n"
    
    for item in page_data:
        kode = item['kode'][:10]  # Limit to 10 chars
        ma3_str = f"{item['ma3']:.2f}"
        ma20_str = f"{item['ma20']:.2f}"
        
        message += f"{kode:<10} {ma3_str:<12} {ma20_str:<12}\n"
    
    message += "```"
    
    # Create navigation buttons if multiple pages
    keyboard = None
    if total_pages > 1:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = []
        
        # Previous button
        if page > 1:
            buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"nempel_{command_type}_page_{page-1}"))
        
        # Page info
        buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        
        # Next button
        if page < total_pages:
            buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"nempel_{command_type}_page_{page+1}"))
        
        keyboard = InlineKeyboardMarkup([buttons])
    
    return message, keyboard

@is_authorized_user
@spy
@vip
async def nempel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /nempel command (5% threshold)"""
    
    # Send processing message
    processing_msg = await update.message.reply_text("📊 Menganalisis nempel MA... Mohon tunggu...")
    
    try:
        # Calculate nempel analysis with 5% threshold
        nempel_data, error = calculate_nempel_analysis(0.05)  # 5%
        
        if error:
            await processing_msg.edit_text(f"❌ {error}")
            return
        
        if not nempel_data:
            await processing_msg.edit_text("📊 Tidak ada saham yang memenuhi kriteria nempel analysis")
            return
        
        # Get total files processed
        directory = "/home/ec2-user/database/wl"
        excel_files = get_excel_files(directory)
        total_files = min(len(excel_files), 30)
        
        # Edit processing message with result
        message, keyboard = format_nempel_message(nempel_data, total_files, "nempel")
        await processing_msg.edit_text(message, parse_mode='Markdown', reply_markup=keyboard)
        
        # Store data for pagination if needed
        if keyboard:
            context.user_data[f'nempel_nempel_data'] = nempel_data
            context.user_data[f'nempel_nempel_files'] = total_files
        
        # Cleanup (but keep pagination data temporarily)
        import gc
        gc.collect()
        
    except Exception as e:
        logger.error(f"Error in nempel_command: {e}")
        await processing_msg.edit_text("❌ Fitur sedang dalam perbaikan")

async def nempel_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for nempel results"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback data: nempel_{command_type}_page_{page_num}
        parts = query.data.split('_')
        if len(parts) != 4 or parts[0] != 'nempel' or parts[2] != 'page':
            return
            
        command_type = parts[1]  # nempel or snempel
        page = int(parts[3])
        
        # Get stored data
        data_key = f'nempel_{command_type}_data'
        files_key = f'nempel_{command_type}_files'
        
        if data_key not in context.user_data or files_key not in context.user_data:
            await query.edit_message_text("❌ Data sudah expired, silakan jalankan ulang command")
            return
        
        nempel_data = context.user_data[data_key]
        total_files = context.user_data[files_key]
        
        # Format message for requested page
        message, keyboard = format_nempel_message(nempel_data, total_files, command_type, page)
        
        await query.edit_message_text(
            message, 
            parse_mode='Markdown', 
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in nempel_pagination_callback: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat navigasi")

@is_authorized_user
@spy
@vip
async def snempel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /snempel command (3% threshold)"""
    
    # Send processing message
    processing_msg = await update.message.reply_text("🚀 Menganalisis super nempel MA... Mohon tunggu...")
    
    try:
        # Calculate nempel analysis with 3% threshold
        nempel_data, error = calculate_nempel_analysis(0.03)  # 3%
        
        if error:
            await processing_msg.edit_text(f"❌ {error}")
            return
        
        if not nempel_data:
            await processing_msg.edit_text("📊 Tidak ada saham yang memenuhi kriteria super nempel analysis")
            return
        
        # Get total files processed
        directory = "/home/ec2-user/database/wl"
        excel_files = get_excel_files(directory)
        total_files = min(len(excel_files), 30)
        
        # Edit processing message with result
        message, keyboard = format_nempel_message(nempel_data, total_files, "snempel")
        await processing_msg.edit_text(message, parse_mode='Markdown', reply_markup=keyboard)
        
        # Store data for pagination if needed
        if keyboard:
            context.user_data[f'nempel_snempel_data'] = nempel_data
            context.user_data[f'nempel_snempel_files'] = total_files
        
        # Cleanup (but keep pagination data temporarily)
        import gc
        gc.collect()
        
    except Exception as e:
        logger.error(f"Error in snempel_command: {e}")
        await processing_msg.edit_text("❌ Fitur sedang dalam perbaikan")