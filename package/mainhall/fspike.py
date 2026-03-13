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

import json

def read_txt_data_combined(file_path):
    """Read txt (JSON) data and extract required columns"""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)

        df = pd.DataFrame(data)

        if not all(col in df.columns for col in ['kode_saham', 'penutupan', 'volume', 'foreign_sell', 'foreign_buy']):
            logger.error(f"File {file_path} missing required columns")
            return None

        # Ambil kolom yang dibutuhkan
        result_df = df[['kode_saham', 'penutupan', 'volume', 'foreign_sell', 'foreign_buy']].copy()

        # Bersihkan data
        result_df = result_df.dropna(subset=['kode_saham'])
        numeric_cols = ['penutupan', 'volume', 'foreign_sell', 'foreign_buy']
        for col in numeric_cols:
            result_df[col] = pd.to_numeric(result_df[col], errors='coerce').fillna(0)

        # Hitung net foreign
        result_df['foreign_net'] = result_df['foreign_buy'] - result_df['foreign_sell']

        return result_df

    except Exception as e:
        logger.error(f"Error reading txt {file_path}: {e}")
        return None


def get_txt_files(directory):
    """Get all txt files and sort by date"""
    files = []
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):
            file_date = get_file_date_from_name(filename.replace('.txt', '.xlsx'))
            if file_date:
                files.append({
                    'filename': filename,
                    'date': file_date,
                    'path': os.path.join(directory, filename)
                })
    files.sort(key=lambda x: x['date'], reverse=True)
    return files


def calculate_vsa_for_stocks(all_volume_data):
    """Calculate VSA for all stocks - NO FILTER, calculate for all stocks"""
    vsa_results = {}
    
    for stock_code, volumes in all_volume_data.items():
        try:
            # Harus ada minimal 7 data untuk bisa dihitung
            if len(volumes) < 7:
                vsa_results[stock_code] = 0  # Set 0 instead of skip
                continue
            
            # Volume hari ini (data pertama karena file diurutkan terbaru dulu)
            vol_today = volumes[0]
            
            # Rata-rata 7 hari (7 data terbaru)
            avg_7_days = sum(volumes[:7]) / 7
            avg_30_days = sum(volumes[:30]) / 30 if len(volumes) >= 30 else sum(volumes) / len(volumes)
            
            # Rata-rata 60 hari (atau semua data yang ada jika < 60)
            max_days = min(len(volumes), 60)
            avg_60_days = sum(volumes[:max_days]) / max_days
            
            # REMOVE FILTER - Calculate VSA for ALL stocks
            # Hitung spike
            spike_today = vol_today / avg_7_days if avg_7_days > 0 else 0
            spike_7vs30 = avg_7_days / avg_30_days if avg_30_days > 0 else 0
            spike_7vs60 = avg_7_days / avg_60_days if avg_60_days > 0 else 0
            
            # VSA = (Spike 1 + Spike 2 + Spike 3) / 3
            vsa_value = (spike_today + spike_7vs60 + spike_7vs30) / 3
            vsa_results[stock_code] = vsa_value
        
        except Exception as e:
            logger.warning(f"Error processing VSA for {stock_code}: {e}")
            vsa_results[stock_code] = 0  # Set 0 on error instead of skip
            continue
    
    return vsa_results

def calculate_foreign_spike_with_vsa():
    """Calculate foreign spike analysis with VSA - returns positive spikes and reversals separately"""
    directory = "/home/ec2-user/database/cache"
    
    try:
        # Ambil semua txt files
        txt_files = get_txt_files(directory)
        
        if len(txt_files) < 2:
            return None, None, "Tidak cukup data untuk analisis spike (minimal 2 file)"
        
        # Maksimal 60 file
        txt_files = txt_files[:60]
        logger.info(f"Processing {len(txt_files)} files for spike and VSA analysis")
        
        all_foreign_data = {}
        all_volume_data = {}
        latest_prices = {}
        file_count_per_stock = {}
        
        for i, file_info in enumerate(txt_files):
            logger.info(f"Processing {file_info['filename']} ({i+1}/{len(txt_files)})")
            
            df = read_txt_data_combined(file_info['path'])
            if df is None:
                continue
            
            if i == 0:  # File terbaru
                latest_prices = dict(zip(df['kode_saham'], df['penutupan']))
            
            for _, row in df.iterrows():
                kode = row['kode_saham']
                net = row['foreign_net']
                volume = row['volume']
                
                if kode not in all_foreign_data:
                    all_foreign_data[kode] = []
                    file_count_per_stock[kode] = 0
                
                all_foreign_data[kode].append(net)
                file_count_per_stock[kode] += 1
                
                if volume > 0:
                    if kode not in all_volume_data:
                        all_volume_data[kode] = []
                    all_volume_data[kode].append(volume)
        
        if not all_foreign_data:
            return None, None, "Tidak ada data yang berhasil diproses"
        
        # Calculate VSA for all stocks
        logger.info("Calculating VSA...")
        vsa_results = calculate_vsa_for_stocks(all_volume_data)
        
        # Calculate foreign spikes
        positive_spikes = []  # Normal spikes (avg > 0, latest > avg)
        reversal_spikes = []  # Reversal spikes (avg < 0, latest > 0)
        
        latest_file = txt_files[0]
        latest_df = read_txt_data_combined(latest_file['path'])
        
        if latest_df is None:
            return None, None, "Gagal membaca file terbaru"
        
        for _, row in latest_df.iterrows():
            kode = row['kode_saham']
            latest_net = row['foreign_net']
            
            if kode in all_foreign_data and len(all_foreign_data[kode]) > 0:
                avg_net = sum(all_foreign_data[kode]) / len(all_foreign_data[kode])
                data_count = file_count_per_stock[kode]
                
                # Calculate spike ratio
                if avg_net != 0:
                    spike_ratio = latest_net / avg_net
                else:
                    # Handle division by zero
                    if latest_net > 0:
                        spike_ratio = float('inf')
                    elif latest_net < 0:
                        spike_ratio = float('-inf')
                    else:
                        spike_ratio = 0
                
                # Only include if latest_net is positive (foreign buy today)
                if latest_net > 0:
                    # Get VSA value for this stock (default 0 if not calculated)
                    vsa_value = vsa_results.get(kode, 0)
                    
                    spike_data = {
                        'kode': kode,
                        'latest_net': latest_net,
                        'avg_net': avg_net,
                        'spike_ratio': spike_ratio,
                        'price': latest_prices.get(kode, 0),
                        'data_count': data_count,
                        'vsa': vsa_value  # Add VSA to spike data
                    }
                    
                    if avg_net > 0:
                        # POSITIVE SPIKE: avg positif, latest lebih besar
                        if spike_ratio >= 2.5:
                            positive_spikes.append(spike_data)
                    else:
                        # REVERSAL SPIKE: avg negatif, latest positif
                        # Untuk reversal, kita pakai abs karena pembagian pos/neg = negatif
                        if abs(spike_ratio) >= 2.5:
                            reversal_spikes.append(spike_data)
        
        # Sort both categories by spike ratio (highest first)
        positive_spikes.sort(key=lambda x: x['spike_ratio'], reverse=True)
        reversal_spikes.sort(key=lambda x: abs(x['spike_ratio']), reverse=True)
        
        return positive_spikes, reversal_spikes, None
        
    except Exception as e:
        logger.error(f"Error in calculate_foreign_spike_with_vsa: {e}")
        return None, None, "Fitur sedang dalam perbaikan"

def format_spike_message_with_vsa(spike_data, total_files, spike_type, page=1, items_per_page=15):
    """Format spike results into message with pagination - VSA instead of Hari"""
    if not spike_data:
        if spike_type == "positive":
            return [f"Tidak ada saham dengan foreign buy spike positif ≥ 2.5x"]
        else:
            return [f"Tidak ada saham dengan foreign buy spike reversal ≥ 2.5x"]
    
    # Calculate pagination
    total_items = len(spike_data)
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    page_data = spike_data[start_idx:end_idx]
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    if spike_type == "positive":
        title = "🚀 FOREIGN BUY SPIKE POSITIF (≥2.5x)"
        subtitle = "Spike asing"
    else:
        title = "🔄 FOREIGN BUY SPIKE REVERSAL (≥2.5x)"  
        subtitle = "Reversal Spike"
    
    message = f"```\n{title}\n"
    message += f"{subtitle} | Data: {total_files} hari | Hal {page}/{total_pages}\n"
    message += "="*50 + "\n"
    message += f"{'Kode':<6} {'Price':<8} {'Latest':<10} {'Avg60':<10} {'Spike':<8} {'VSA':<5}\n"
    message += "="*50 + "\n"
    
    for item in page_data:
        kode = item['kode'][:6]  # Limit to 6 chars
        price = f"{item['price']:,.0f}" if item['price'] > 0 else "-"
        latest = f"{item['latest_net']:,.0f}"
        avg = f"{item['avg_net']:,.0f}"
        
        # Format spike ratio
        if item['spike_ratio'] == float('inf'):
            spike = "∞+"
        elif item['spike_ratio'] == float('-inf'):
            spike = "∞-"
        else:
            if spike_type == "reversal":
                # Untuk reversal, tampilkan abs value tapi beri tanda R
                spike = f"{abs(item['spike_ratio']):.1f}R"
            else:
                spike = f"{item['spike_ratio']:.1f}x"
        
        # Format VSA
        vsa_str = f"{item['vsa']:.2f}"
        
        message += f"{kode:<6} {price:<8} {latest:<10} {avg:<10} {spike:<8} {vsa_str:<5}\n"
    
    message += "```\n\n"
    
    if page == 1:  # Only show legend on first page
        if spike_type == "positive":
            message += "🚀 Spike: Foreign buy meningkat dari rata-rata positif\n"
        else:
            message += "🔄 Reversal: Foreign berubah dari jual ke beli besar\n"
        message += "📊 VSA: Volume-Speed Analysis indicator\n"
    
    if total_pages > 1:
        message += f"Showing {start_idx + 1}-{end_idx} of {total_items} stocks"
    
    return message

@is_authorized_user
@spy
@vip
@with_queue_control
async def fspike_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /fspike command with VSA"""
    
    # Send processing message
    processing_msg = await update.message.reply_text("🔥 Menganalisis foreign spike & VSA... Mohon tunggu...")
    
    try:
        # Calculate spike with VSA
        positive_spikes, reversal_spikes, error = calculate_foreign_spike_with_vsa()
        
        if error:
            await processing_msg.edit_text(f"⚠️ {error}")
            return
        
        # Get total files processed
        directory = "/home/ec2-user/database/cache"
        txt_files = get_txt_files(directory)
        total_files = min(len(txt_files), 60)

        # Delete processing message
        await processing_msg.delete()
        
        # Send summary first
        pos_count = len(positive_spikes) if positive_spikes else 0
        rev_count = len(reversal_spikes) if reversal_spikes else 0
        
        summary_msg = f"🚀 **FOREIGN BUY SPIKE ANALYSIS + VSA**\n"
        summary_msg += f"📈 Spike Positif: {pos_count} saham\n"
        summary_msg += f"🔄 Spike Reversal: {rev_count} saham\n"
        summary_msg += f"📅 Data dari {total_files} hari terakhir"
        await update.message.reply_text(summary_msg, parse_mode='Markdown')
        
        items_per_page = 15
        
        # Send POSITIVE SPIKES first
        if positive_spikes:
            total_pages = (len(positive_spikes) + items_per_page - 1) // items_per_page
            
            for page in range(1, total_pages + 1):
                message = format_spike_message_with_vsa(positive_spikes, total_files, "positive", page, items_per_page)
                await update.message.reply_text(message, parse_mode='Markdown')
                
                # Add small delay between messages
                import asyncio
                await asyncio.sleep(0.1)
        else:
            await update.message.reply_text("📊 Tidak ada saham dengan foreign buy spike positif ≥ 2.5x")
        
        # Send REVERSAL SPIKES second
        if reversal_spikes:
            total_pages = (len(reversal_spikes) + items_per_page - 1) // items_per_page
            
            for page in range(1, total_pages + 1):
                message = format_spike_message_with_vsa(reversal_spikes, total_files, "reversal", page, items_per_page)
                await update.message.reply_text(message, parse_mode='Markdown')
                
                # Add small delay between messages
                import asyncio
                await asyncio.sleep(0.1)
        else:
            await update.message.reply_text("📊 Tidak ada saham dengan foreign buy spike reversal ≥ 2.5x")
            
        # Cleanup
        del positive_spikes, reversal_spikes
        import gc
        gc.collect()
        
    except Exception as e:
        logger.error(f"Error in fspike_command: {e}")
        await processing_msg.edit_text("⚠️ Fitur sedang dalam perbaikan")