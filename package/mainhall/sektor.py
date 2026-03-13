from imporh import*

# Daftar sektor yang akan ditampilkan
SEKTOR_LIST = [
    'IDXENERGY', 'IDXBASIC', 'IDXINDUST', 'IDXONCYC', 'IDXCYCLIC',
    'IDXHEALTH', 'IDXFINANCE', 'IDXPROPERT', 'IDXTECHNO', 'IDXINFRA', 'IDXTRANS'
]

def load_sektor_data(max_days=60):
    """Load data sektor dari file Excel dalam direktori database/sektor"""
    base_path = "/home/ec2-user/database/sektor"
    
    if not os.path.exists(base_path):
        return None, "Direktori sektor tidak ditemukan"
    
    # Cari semua file xlsx dalam direktori
    xlsx_files = glob.glob(os.path.join(base_path, "*.xlsx"))
    
    if not xlsx_files:
        return None, "Tidak ada file data sektor ditemukan"
    
    # Sort file berdasarkan nama (tanggal ddmmyy)
    xlsx_files.sort(reverse=True)  # Terbaru dulu
    
    # Ambil maksimal 60 file terakhir
    xlsx_files = xlsx_files[:max_days]
    
    all_data = []
    
    for file_path in xlsx_files:
        try:
            # Extract tanggal dari nama file
            filename = os.path.basename(file_path)
            date_str = filename.replace('.xlsx', '')
            
            # Parse tanggal ddmmyy
            if len(date_str) == 6:
                day = int(date_str[:2])
                month = int(date_str[2:4])
                year = 2000 + int(date_str[4:6])  # Asumsi tahun 20xx
                file_date = datetime(year, month, day)
            else:
                continue
            
            # Baca file Excel
            df = pd.read_excel(file_path)
            
            # Filter hanya sektor yang diinginkan
            df_filtered = df[df.iloc[:, 1].isin(SEKTOR_LIST)].copy()  # Kolom B (index 1)
            
            if not df_filtered.empty:
                df_filtered['Tanggal'] = file_date
                df_filtered['Kode_Indeks'] = df_filtered.iloc[:, 1]  # Kolom B
                df_filtered['Penutupan'] = pd.to_numeric(df_filtered.iloc[:, 5], errors='coerce')  # Kolom F
                df_filtered['Volume'] = pd.to_numeric(df_filtered.iloc[:, 8], errors='coerce')  # Kolom I
                df_filtered['Frekuensi'] = pd.to_numeric(df_filtered.iloc[:, 10], errors='coerce')  # Kolom K
                df_filtered['Nilai'] = pd.to_numeric(df_filtered.iloc[:, 9], errors='coerce')  # Kolom J
                df_filtered['Kapitalisasi'] = pd.to_numeric(df_filtered.iloc[:, 8], errors='coerce')  # Kolom I (sama dengan Volume berdasarkan permintaan)
                
                all_data.append(df_filtered[['Tanggal', 'Kode_Indeks', 'Penutupan', 'Volume', 'Frekuensi', 'Nilai', 'Kapitalisasi']])
                
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue
    
    if not all_data:
        return None, "Tidak ada data valid yang bisa dimuat"
    
    # Gabungkan semua data
    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df = combined_df.sort_values(['Kode_Indeks', 'Tanggal'])
    
    return combined_df, None

def calculate_spike_metrics(df, sektor_code):
    """Hitung spike metrics untuk sektor tertentu"""
    sektor_data = df[df['Kode_Indeks'] == sektor_code].copy()
    
    if len(sektor_data) < 7:
        return None
    
    sektor_data = sektor_data.sort_values('Tanggal')
    
    metrics = {}
    
    # Untuk setiap metrik (Volume, Frekuensi, Nilai, Kapitalisasi)
    metric_columns = ['Volume', 'Frekuensi', 'Nilai', 'Kapitalisasi']
    
    for metric in metric_columns:
        values = sektor_data[metric].dropna()
        
        if len(values) < 7:
            continue
            
        # Hitung rata-rata
        if len(values) >= 60:
            avg_60 = values.tail(60).mean()
            avg_30 = values.tail(30).mean()
            avg_7 = values.tail(7).mean()
        elif len(values) >= 30:
            avg_60 = values.mean()  # Gunakan semua data yang ada
            avg_30 = values.tail(30).mean()
            avg_7 = values.tail(7).mean()
        elif len(values) >= 7:
            avg_60 = values.mean()
            avg_30 = values.mean()
            avg_7 = values.tail(7).mean()
        else:
            continue
        
        # Hitung spike
        spike_60_to_30 = ((avg_30 - avg_60) / avg_60 * 100) if avg_60 > 0 else 0
        spike_7_to_last = ((values.iloc[-1] - avg_7) / avg_7 * 100) if avg_7 > 0 else 0
        
        # Rata-rata spike
        final_spike = (spike_60_to_30 + spike_7_to_last) / 2
        
        metrics[metric] = {
            'avg_60': avg_60,
            'avg_30': avg_30,
            'avg_7': avg_7,
            'last_value': values.iloc[-1],
            'spike_60_to_30': spike_60_to_30,
            'spike_7_to_last': spike_7_to_last,
            'final_spike': final_spike
        }
    
    # Hitung rata-rata final spike dari semua metrik
    if metrics:
        total_spike = sum([m['final_spike'] for m in metrics.values()])
        avg_final_spike = total_spike / len(metrics)
        
        return {
            'sektor': sektor_code,
            'last_price': sektor_data['Penutupan'].iloc[-1] if not sektor_data['Penutupan'].empty else 0,
            'metrics': metrics,
            'avg_spike': avg_final_spike
        }
    
    return None

@is_authorized_user
@spy
@vip
@with_queue_control
async def sektor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /sektor"""
    user_id = update.effective_user.id
    
    # Check access level jika diperlukan
    # access_level = check_access_level(user_id)
    # if access_level < 2:  # Uncomment jika ingin membatasi akses
    #     await update.message.reply_text("⛔ Fitur ini hanya untuk user VIP")
    #     return
    
    await update.message.reply_text("🔄 Loading data sektor...")
    
    try:
        # Load data
        df, error = load_sektor_data()
        if error:
            await update.message.reply_text(f"❌ Error: {error}")
            return
        
        # Hitung spike untuk semua sektor
        results = []
        for sektor in SEKTOR_LIST:
            spike_data = calculate_spike_metrics(df, sektor)
            if spike_data:
                results.append(spike_data)
        
        if not results:
            await update.message.reply_text("❌ Tidak ada data spike yang bisa dihitung")
            return
        
        # Sort berdasarkan avg_spike tertinggi
        results.sort(key=lambda x: x['avg_spike'], reverse=True)
        
        # Format output dengan font monospace
        message = "📊 **ANALISIS SEKTOR - SPIKE ANALYSIS**\n\n"
        message += "```\n"
        message += "SEKTOR      | PRICE    | SPIKE%\n"
        message += "------------|----------|--------\n"
        
        for result in results:
            sektor = result['sektor']
            price = result['last_price']
            spike = result['avg_spike']
            
            # Format dengan padding untuk alignment
            sektor_padded = sektor.ljust(11)
            price_str = f"{price:,.0f}".rjust(9)
            spike_str = f"{spike:+.1f}%".rjust(7)
            
            message += f"{sektor_padded}| {price_str} | {spike_str}\n"
        
        message += "```\n"
        message += "\n💡 Spike = rata-rata dari Volume, Frekuensi, Nilai, Kapitalisasi"
        message += f"\n📅 Data terakhir: {df['Tanggal'].max().strftime('%d/%m/%Y')}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        gc.collect()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        
@is_authorized_user
@spy
@vip
@with_queue_control
async def sektor_detail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk detail sektor tertentu"""
    if not context.args:
        await update.message.reply_text(
            "📋 Gunakan format: /detail_sektor KODE_SEKTOR\n\n"
            "Contoh: `/detail_sektor IDXENERGY`\n\n"
            "Sektor tersedia:\n" + ", ".join(SEKTOR_LIST),
            parse_mode='Markdown'
        )
        return
    
    sektor_code = context.args[0].upper()
    
    if sektor_code not in SEKTOR_LIST:
        await update.message.reply_text(
            f"❌ Sektor '{sektor_code}' tidak tersedia\n\n"
            "Sektor tersedia:\n" + ", ".join(SEKTOR_LIST)
        )
        return
    
    await update.message.reply_text(f"🔄 Loading detail untuk {sektor_code}...")
    
    try:
        # Load data
        df, error = load_sektor_data()
        if error:
            await update.message.reply_text(f"❌ Error: {error}")
            return
        
        # Hitung detail untuk sektor yang diminta
        spike_data = calculate_spike_metrics(df, sektor_code)
        
        if not spike_data:
            await update.message.reply_text(f"❌ Tidak ada data untuk sektor {sektor_code}")
            return
        
        # Format detail output
        message = f"📈 **DETAIL ANALISIS - {sektor_code}**\n\n"
        message += f"💰 **Harga Terakhir:** {spike_data['last_price']:,.0f}\n"
        message += f"🔥 **Total Spike:** {spike_data['avg_spike']:+.1f}%\n\n"
        
        message += "```\n"
        message += "METRIK     | AVG60  | AVG30  | AVG7   | LAST   | SPIKE%\n"
        message += "-----------|--------|--------|--------|--------|---------\n"
        
        for metric, data in spike_data['metrics'].items():
            metric_short = metric[:10].ljust(10)
            avg_60 = f"{data['avg_60']:.0f}".rjust(7)
            avg_30 = f"{data['avg_30']:.0f}".rjust(7)
            avg_7 = f"{data['avg_7']:.0f}".rjust(7)
            last = f"{data['last_value']:.0f}".rjust(7)
            spike = f"{data['final_spike']:+.1f}%".rjust(8)
            
            message += f"{metric_short}|{avg_60}|{avg_30}|{avg_7}|{last}|{spike}\n"
        
        message += "```\n"
        message += f"\n📅 Data terakhir: {df['Tanggal'].max().strftime('%d/%m/%Y')}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        gc.collect()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
