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
        # B=1 (Kode Saham), K=10 (Penutupan), M=12 (Volume), X=23 (Foreign Sell), Y=24 (Foreign Buy)
        if df.shape[1] >= 25:  # Ensure we have enough columns
            data = {
                'kode_saham': df.iloc[:, 1],      # Column B
                'penutupan': df.iloc[:, 10],      # Column K
                'volume': df.iloc[:, 12],         # Column M
                'foreign_sell': df.iloc[:, 23],   # Column X
                'foreign_buy': df.iloc[:, 24]     # Column Y
            }
            
            # Create dataframe and clean data
            result_df = pd.DataFrame(data)
            
            # Remove rows with empty kode_saham
            result_df = result_df.dropna(subset=['kode_saham'])
            
            # Convert numeric columns, replace NaN with 0
            numeric_cols = ['penutupan', 'volume', 'foreign_sell', 'foreign_buy']
            for col in numeric_cols:
                result_df[col] = pd.to_numeric(result_df[col], errors='coerce').fillna(0)
            
            # Calculate foreign net
            result_df['foreign_net'] = result_df['foreign_buy'] - result_df['foreign_sell']
            
            return result_df
        else:
            logger.error(f"File {file_path} doesn't have enough columns")
            return None
            
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return None

def check_price_stability(prices, max_increase=0.05):
    """Check if price didn't increase more than max_increase (5%) in the period"""
    if len(prices) < 2:
        return True
    
    # Check if total increase from oldest to newest is <= 5%
    oldest_price = prices[-1]  # Last item (oldest date)
    newest_price = prices[0]   # First item (newest date)
    
    if oldest_price > 0:  # Avoid division by zero
        total_increase = (newest_price - oldest_price) / oldest_price
        return total_increase <= max_increase
    
    return True

def calculate_foreign_spike_analysis(data_by_date):
    """Calculate FSA (Foreign Spike Analysis) using 7-day vs 30-day averages"""
    fsa_results = {}
    
    for kode, daily_data in data_by_date.items():
        if len(daily_data) < 7:  # Need at least 7 days of data
            continue
            
        # Get foreign_net values (newest first)
        foreign_nets = [day['foreign_net'] for day in daily_data]
        
        # Today's foreign net
        today_net = foreign_nets[0]
        
        # 7-day average
        avg_7_days = sum(foreign_nets[:7]) / 7
        
        # 30-day average (or all available data if less than 30)
        max_days = min(len(foreign_nets), 30)
        avg_30_days = sum(foreign_nets[:max_days]) / max_days
        
        # Calculate spikes
        if avg_7_days != 0:
            spike_today_vs_7 = today_net / avg_7_days
        else:
            spike_today_vs_7 = float('inf') if today_net > 0 else 0
            
        if avg_30_days != 0:
            spike_7_vs_30 = avg_7_days / avg_30_days
        else:
            spike_7_vs_30 = float('inf') if avg_7_days > 0 else 0
        
        # FSA = (spike1 + spike2) / 2
        if spike_today_vs_7 == float('inf') or spike_7_vs_30 == float('inf'):
            fsa = float('inf')
        else:
            fsa = (spike_today_vs_7 + spike_7_vs_30) / 2
        
        # Only include positive foreign net with FSA >= 2.5
        if today_net > 0 and abs(fsa) >= 2.5:
            fsa_results[kode] = fsa
    
    return fsa_results

def calculate_volume_spike_analysis(data_by_date):
    """Calculate VSA (Volume Spike Analysis) using same logic as vol.py"""
    vsa_results = {}
    
    for kode, daily_data in data_by_date.items():
        if len(daily_data) < 7:  # Need at least 7 days of data
            continue
            
        # Get volume values (newest first)
        volumes = [day['volume'] for day in daily_data if day['volume'] > 0]
        
        if len(volumes) < 7:
            continue
            
        # Today's volume
        vol_today = volumes[0]
        
        # 7-day average
        avg_7_days = sum(volumes[:7]) / 7
        
        # 30-day average (or all available data if less than 30)
        max_days = min(len(volumes), 30)
        avg_30_days = sum(volumes[:max_days]) / max_days
        
        # Filter: Avg 7hr > Avg 30hr AND Vol today > Avg 7hr
        if avg_7_days > avg_30_days and vol_today > avg_7_days:
            # Calculate spikes
            spike_today = vol_today / avg_7_days if avg_7_days > 0 else 0
            spike_7vs30 = avg_7_days / avg_30_days if avg_30_days > 0 else 0
            
            # VSA = (spike1 + spike2) / 2
            vsa = (spike_today + spike_7vs30) / 2
            
            if vsa >= 2.2:
                vsa_results[kode] = vsa
    
    return vsa_results

def calculate_super_analysis():
    """Main function to calculate super analysis combining FSA and VSA"""
    directory = "/home/ec2-user/database/wl"
    
    try:
        # Get all excel files (limit to 30 files)
        excel_files = get_excel_files(directory)
        
        if len(excel_files) < 7:
            return None, "Tidak cukup data untuk analisis (minimal 7 file)"
        
        # Take maximum 30 files
        excel_files = excel_files[:30]
        logger.info(f"Processing {len(excel_files)} files for super analysis")
        
        # Collect all data organized by date
        data_by_date = {}  # {kode: [day0_data, day1_data, ...]}
        
        # Process each file
        for i, file_info in enumerate(excel_files):
            logger.info(f"Processing {file_info['filename']} ({i+1}/{len(excel_files)})")
            
            df = read_excel_data(file_info['path'])
            if df is None:
                continue
            
            # Store data for each stock
            for _, row in df.iterrows():
                kode = row['kode_saham']
                
                if kode not in data_by_date:
                    data_by_date[kode] = []
                
                data_by_date[kode].append({
                    'penutupan': row['penutupan'],
                    'volume': row['volume'],
                    'foreign_net': row['foreign_net'],
                    'date_index': i
                })
        
        if not data_by_date:
            return None, "Tidak ada data yang berhasil diproses"
        
        # Calculate FSA and VSA
        fsa_results = calculate_foreign_spike_analysis(data_by_date)
        vsa_results = calculate_volume_spike_analysis(data_by_date)
        
        # Find stocks that meet both criteria but exclude those with >5% price increase
        super_results = []
        
        for kode in data_by_date.keys():
            if kode in fsa_results and kode in vsa_results:
                # Check price stability (exclude if increased >5% in 30 days)
                prices = [day['penutupan'] for day in data_by_date[kode]]
                
                if check_price_stability(prices):  # Only include if price increase <= 5%
                    super_results.append({
                        'kode': kode,
                        'fsa': fsa_results[kode],
                        'vsa': vsa_results[kode],
                        'price': data_by_date[kode][0]['penutupan']  # Latest price
                    })
        
        # Sort by kode (stock name)
        super_results.sort(key=lambda x: x['kode'])
        
        return super_results, None
        
    except Exception as e:
        logger.error(f"Error in calculate_super_analysis: {e}")
        return None, "Fitur sedang dalam perbaikan"

def format_super_message(super_data, total_files):
    """Format super results into message"""
    if not super_data:
        return "Tidak ada saham yang memenuhi kriteria FSA ≥ 2.5x, VSA ≥ 2.2x, dan harga stabil"
    
    message = f"```\n🚀 SUPER ANALYSIS\n"
    message += f"Data: {total_files} hari | Total: {len(super_data)} saham\n"
    message += "=" * 45 + "\n"
    message += f"{'Kode':<8} {'FSA':<8} {'VSA':<8} {'Price':<8}\n"
    message += "=" * 45 + "\n"
    
    for item in super_data:
        kode = item['kode'][:8]  # Limit to 8 chars
        
        # Format FSA
        if item['fsa'] == float('inf'):
            fsa_str = "∞"
        else:
            fsa_str = f"{item['fsa']:.2f}"
        
        vsa_str = f"{item['vsa']:.2f}"
        price_str = f"{item['price']:,.0f}" if item['price'] > 0 else "-"
        
        message += f"{kode:<8} {fsa_str:<8} {vsa_str:<8} {price_str:<8}\n"
    
    message += "```"
    
    return message

@is_authorized_user
@spy
@with_queue_control
async def super_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /super command"""
    
    # Send processing message
    processing_msg = await update.message.reply_text("🔥 Menganalisis super spike... Mohon tunggu...")
    
    try:
        # Calculate super analysis
        super_data, error = calculate_super_analysis()
        
        if error:
            await processing_msg.edit_text(f"❌ {error}")
            return
        
        if not super_data:
            await processing_msg.edit_text("📊 Tidak ada saham yang memenuhi kriteria super analysis")
            return
        
        # Get total files processed
        directory = "/home/ec2-user/database/wl"
        excel_files = get_excel_files(directory)
        total_files = min(len(excel_files), 30)
        
        # Delete processing message
        await processing_msg.delete()
        
        # Format and send message
        message = format_super_message(super_data, total_files)
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Cleanup
        del super_data
        import gc
        gc.collect()
        
    except Exception as e:
        logger.error(f"Error in super_command: {e}")
        await processing_msg.edit_text("❌ Fitur sedang dalam perbaikan")