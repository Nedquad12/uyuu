from imporh import *
from cache import read_or_cache, preload_cache
import json

# Global cache untuk menyimpan SEMUA data VSA
vsa_cache = {}  # {stock_code: {'chg': float, 'vol': float, 'v60': float, 'vsa': float}}

@is_authorized_user 
@spy      
@vip       
@with_queue_control
async def vol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk analisis spike volume"""
    result_data = []
    volume_data = {}
    
    try:
        await update.message.reply_text("🔄 Menganalisis data volume... Mohon tunggu sebentar...")
        
        # Ambil data volume dan simpan SEMUA ke cache
        result_data = analyze_volume_spike()
        
        if not result_data:
            await update.message.reply_text("❌ Tidak ada data yang memenuhi kriteria atau terjadi error saat memproses data")
            return
        
        # Filter HANYA untuk output (VSA >= 1.7)
        filtered_results = [(code, chg, vol, v60, vsa) for code, chg, vol, v60, vsa in result_data if vsa >= 1.7]
        
        if not filtered_results:
            await update.message.reply_text("❌ Tidak ada saham dengan VSA >= 1.7")
            return
        
        # Format header dengan monospace
        header_message = "📊 **Hot Stock, Filter with VSA**\n\n"
        header_message += f"Total saham terfilter: {len(filtered_results)}\n"
        header_message += f"Total saham di cache: {len(vsa_cache)}\n\n"
        
        await update.message.reply_text(header_message, parse_mode='Markdown')
        
        # Format data dengan monospace dan split jika perlu
        data_lines = []
        data_lines.append("Kode     Chg    Vol     V60     VSA")
        data_lines.append("─────────────────────────────────────")
        
        for stock_code, chg, vol, v60, vsa in filtered_results:
            data_lines.append(f"{stock_code:<8} {chg:>4.0f} {vol:>7.2f} {v60:>7.2f} {vsa:>7.2f}")
        
        # Split data ke beberapa message jika terlalu panjang
        max_lines_per_message = 45  # Sekitar 3800 karakter per message
        current_message_lines = []
        message_count = 1
        
        for line in data_lines:
            current_message_lines.append(line)
            
            if len(current_message_lines) >= max_lines_per_message:
                # Kirim message saat ini
                message_content = "```\n" + "\n".join(current_message_lines) + "\n```"
                await update.message.reply_text(message_content, parse_mode='Markdown')
                
                # Reset untuk message berikutnya
                current_message_lines = []
                message_count += 1
        
        # Kirim sisa data jika ada
        if current_message_lines:
            message_content = "```\n" + "\n".join(current_message_lines) + "\n```"
            await update.message.reply_text(message_content, parse_mode='Markdown')
        
        # Kirim footer
        footer_message = f"\n📝 **Keterangan:**\n"
        footer_message += "• Chg = Perubahan harga hari ini\n"
        footer_message += "• Vol = Volume hari ini (juta)\n"
        footer_message += "• V60 = Rata-rata volume 60 hari (juta)\n"
        footer_message += "• VSA = Volume Spike Analysis\n"
        footer_message += "• Data diurutkan berdasarkan VSA tertinggi"
        
        await update.message.reply_text(footer_message, parse_mode='Markdown')
            
    except Exception as e:
        logging.error(f"Error dalam vol_command: {e}")
        await update.message.reply_text(f"❌ Terjadi error: {str(e)}")
    finally:
        # Hapus data hasil hitung setelah output
        result_data.clear()
        volume_data.clear()
        # Force garbage collection
        import gc
        gc.collect()

@is_authorized_user
async def reload_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk reload cache"""
    try:
        await update.message.reply_text("🔄 Memuat ulang cache... Mohon tunggu...")
        preload_cache()
        await update.message.reply_text("✅ Cache berhasil dimuat ulang!")
    except Exception as e:
        logging.error(f"Error dalam reload_cache_command: {e}")
        await update.message.reply_text(f"❌ Error reload cache: {str(e)}")

def get_vsa_from_cache(stock_code):
    """Fungsi untuk ambil VSA dari cache (untuk command lain)
    Returns: dict {'chg': float, 'vol': float, 'v60': float, 'vsa': float} atau None
    """
    stock_code = str(stock_code).strip().upper()
    return vsa_cache.get(stock_code, None)

def get_all_vsa_cache():
    """Fungsi untuk ambil semua data VSA cache
    Returns: dict {stock_code: {'chg': float, 'vol': float, 'v60': float, 'vsa': float}}
    """
    return vsa_cache

def analyze_volume_spike():
    """Fungsi utama untuk analisis spike volume - SIMPAN SEMUA KE CACHE"""
    global vsa_cache
    volume_data = {}
    
    try:
        # Clear cache sebelum reload
        vsa_cache.clear()
        
        data_dir = "/home/ec2-user/database/wl"
        cache_dir = "/home/ec2-user/database/cache"
        
        # Ambil semua file txt dari cache
        cache_files = get_sorted_cache_files(cache_dir)
        
        if len(cache_files) < 14:
            print(f"Hanya ditemukan {len(cache_files)} file, minimal butuh 14 file")
            return []
        
        # Ambil maksimal 60 file terbaru
        cache_files = cache_files[:60]
        print(f"Memproses {len(cache_files)} file dari cache...")
        
        # Kumpulkan data volume dari semua file
        volume_data = collect_volume_data_from_cache(cache_dir, cache_files)
        
        if not volume_data:
            print("Tidak ada data volume yang berhasil dikumpulkan")
            return []
        
        # Hitung spike dan SIMPAN SEMUA KE CACHE (tanpa filter)
        result_data = calculate_spike_and_filter(volume_data, len(cache_files))
        
        # Hapus volume_data setelah selesai
        volume_data.clear()
        
        print(f"VSA Cache: {len(vsa_cache)} saham disimpan")
        
        return result_data
        
    except Exception as e:
        print(f"Error dalam analyze_volume_spike: {e}")
        return []
    finally:
        # Pastikan volume_data dihapus
        volume_data.clear()

def get_sorted_cache_files(cache_dir):
    """Ambil dan sort file cache berdasarkan tanggal ddmmyy"""
    try:
        files = [f for f in os.listdir(cache_dir) if f.endswith('.txt')]
        
        # Parse tanggal dan sort (terbaru dulu)
        file_dates = []
        for file in files:
            try:
                date_str = file.replace('.txt', '')
                if len(date_str) == 6:  # ddmmyy
                    # Parse ddmmyy
                    day = int(date_str[:2])
                    month = int(date_str[2:4])
                    year = int(date_str[4:6])
                    
                    # Asumsi tahun 20xx jika < 50, 19xx jika >= 50
                    if year < 50:
                        year += 2000
                    else:
                        year += 1900
                    
                    date_obj = datetime(year, month, day)
                    file_dates.append((file, date_obj))
            except:
                continue
        
        # Sort berdasarkan tanggal (terbaru dulu)
        file_dates.sort(key=lambda x: x[1], reverse=True)
        sorted_files = [f[0] for f in file_dates]
        
        print(f"Ditemukan {len(sorted_files)} file cache valid")
        return sorted_files
        
    except Exception as e:
        print(f"Error dalam get_sorted_cache_files: {e}")
        return []

def collect_volume_data_from_cache(cache_dir, cache_files):
    """Kumpulkan data volume dari file cache JSON"""
    volume_data = {}  # {stock_code: [(vol, chg), (vol, chg), ...]}
    
    try:
        for i, file in enumerate(cache_files):
            try:
                file_path = os.path.join(cache_dir, file)
                
                # Baca file JSON
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Ambil data kode saham dan volume
                if 'kode_saham' in data and 'volume' in data and 'selisih' in data:
                    stock_codes = data['kode_saham']
                    volumes = data['volume']
                    changes = data['selisih']
                    
                    for j, (code, vol, chg) in enumerate(zip(stock_codes, volumes, changes)):
                        # Skip header row
                        if j == 0 or code == 'KODE SAHAM':
                            continue
                            
                        if code and vol is not None and chg is not None:
                            code = str(code).strip().upper()
                            try:
                                vol = float(vol)
                                chg = float(chg)
                                if vol > 0:  # Hanya ambil volume positif
                                    if code not in volume_data:
                                        volume_data[code] = []
                                    # Simpan tuple (volume, change)
                                    volume_data[code].append((vol, chg))
                            except:
                                continue
                
                print(f"File {i+1}/{len(cache_files)}: {file} - processed")
                
            except Exception as e:
                print(f"Error membaca file {file}: {e}")
                continue
        
        return volume_data
        
    except Exception as e:
        print(f"Error dalam collect_volume_data_from_cache: {e}")
        return {}

def calculate_spike_and_filter(volume_data, total_files):
    """Hitung spike dan SIMPAN SEMUA KE CACHE (tanpa filter di sini)
    Filter cuma dilakukan di result_data untuk output
    """
    global vsa_cache
    result_data = []
    
    for stock_code, data_list in volume_data.items():
        try:
            # Harus ada minimal 14 data untuk bisa dihitung
            if len(data_list) < 14:
                continue
            
            # Data hari ini (data pertama karena file diurutkan terbaru dulu)
            vol_today, chg_today = data_list[0]
            
            # Extract volumes only
            volumes = [v for v, c in data_list]
            
            # Rata-rata 7 hari (7 data terbaru)
            avg_7_days = sum(volumes[:7]) / 7
            
            # Rata-rata 14 hari
            avg_14_days = sum(volumes[:14]) / 14
            
            # Rata-rata 60 hari (atau semua data yang ada jika < 60)
            max_days = min(len(volumes), 60)
            avg_60_days = sum(volumes[:max_days]) / max_days
            
            # Hitung spike
            # spike_today vs avg_7_days
            spike_today_vs_7 = vol_today / avg_7_days if avg_7_days > 0 else 0
            
            # spike_7_days vs avg_14_days
            spike_7_vs_14 = avg_7_days / avg_14_days if avg_14_days > 0 else 0
            
            # VSA = (Spike today vs 7 + Spike 7 vs 14) / 2
            vsa = (spike_today_vs_7 + spike_7_vs_14) / 2
            
            # Konversi volume ke juta
            vol_today_juta = vol_today / 1_000_000
            avg_60_juta = avg_60_days / 1_000_000
            
            # SIMPAN KE CACHE (SEMUA SAHAM, tanpa filter)
            vsa_cache[stock_code] = {
                'chg': chg_today,
                'vol': vol_today_juta,
                'v60': avg_60_juta,
                'vsa': vsa
            }
            
            # Filter untuk result_data (kondisi original)
            # Filter: Avg 7hr > Avg 60hr AND Vol hari ini > Avg 7hr
            if avg_7_days > avg_60_days and vol_today > avg_7_days:
                result_data.append((stock_code, chg_today, vol_today_juta, avg_60_juta, vsa))
        
        except Exception as e:
            print(f"Error processing {stock_code}: {e}")
            continue
    
    # Sort berdasarkan VSA tertinggi
    result_data.sort(key=lambda x: x[4], reverse=True)
    
    print(f"Total di cache: {len(vsa_cache)} saham")
    print(f"Total memenuhi kriteria filter: {len(result_data)} saham")
    
    return result_data
