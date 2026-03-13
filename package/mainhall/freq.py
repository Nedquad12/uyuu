from imporh import *
from cache import read_or_cache, preload_cache
import json

@is_authorized_user 
@spy      
@vip       
@with_queue_control
async def freq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk analisis spike frekuensi"""
    result_data = []
    freq_data = {}
    
    try:
        await update.message.reply_text("📄 Menganalisis data frekuensi... Mohon tunggu sebentar...")
        
        # Ambil data frekuensi
        result_data = analyze_frequency_spike()
        
        if not result_data:
            await update.message.reply_text("❌ Tidak ada data yang memenuhi kriteria atau terjadi error saat memproses data")
            return
        
        # Filter berdasarkan minimal spike 1.7
        filtered_results = [(code, chg, freq, f60, fsa) for code, chg, freq, f60, fsa in result_data if fsa >= 1.7]
        
        if not filtered_results:
            await update.message.reply_text("❌ Tidak ada saham dengan FSA >= 1.7")
            return
        
        # Format header dengan monospace
        header_message = "📊 **Hot Stock, Filter with FSA**\n\n"
        header_message += f"Total saham: {len(filtered_results)}\n\n"
        
        await update.message.reply_text(header_message, parse_mode='Markdown')
        
        # Format data dengan monospace dan split jika perlu
        data_lines = []
        data_lines.append("Kode     Chg   Freq    F60     FSA")
        data_lines.append("─────────────────────────────────────")
        
        for stock_code, chg, freq, f60, fsa in filtered_results:
            data_lines.append(f"{stock_code:<8} {chg:>4.0f} {freq:>6.1f} {f60:>6.1f} {fsa:>7.2f}")
        
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
        footer_message = f"\n🔍 **Keterangan:**\n"
        footer_message += "• Chg = Perubahan harga hari ini\n"
        footer_message += "• Freq = Frekuensi transaksi hari ini\n"
        footer_message += "• F60 = Rata-rata frekuensi 60 hari\n"
        footer_message += "• FSA = Frequency Spike Analysis\n"
        footer_message += "• Data diurutkan berdasarkan FSA tertinggi"
        
        await update.message.reply_text(footer_message, parse_mode='Markdown')
            
    except Exception as e:
        logging.error(f"Error dalam freq_command: {e}")
        await update.message.reply_text(f"❌ Terjadi error: {str(e)}")
    finally:
        # Hapus data hasil hitung setelah output
        result_data.clear()
        freq_data.clear()
        # Force garbage collection
        import gc
        gc.collect()

@is_authorized_user
async def reload6_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk reload cache"""
    try:
        await update.message.reply_text("🔄 Memuat ulang cache... Mohon tunggu...")
        preload_cache()
        await update.message.reply_text("✅ Cache berhasil dimuat ulang!")
    except Exception as e:
        logging.error(f"Error dalam reload6_cache_command: {e}")
        await update.message.reply_text(f"❌ Error reload cache: {str(e)}")

def analyze_frequency_spike():
    """Fungsi utama untuk analisis spike frekuensi"""
    freq_data = {}
    
    try:
        cache_dir = "/home/ec2-user/database/cache"
        
        # Ambil semua file txt dari cache
        cache_files = get_sorted_cache_files(cache_dir)
        
        if len(cache_files) < 14:
            print(f"Hanya ditemukan {len(cache_files)} file, minimal butuh 14 file")
            return []
        
        # Ambil maksimal 60 file terbaru
        cache_files = cache_files[:60]
        print(f"Memproses {len(cache_files)} file dari cache...")
        
        # Kumpulkan data frekuensi dari semua file
        freq_data = collect_frequency_data_from_cache(cache_dir, cache_files)
        
        if not freq_data:
            print("Tidak ada data frekuensi yang berhasil dikumpulkan")
            return []
        
        # Hitung spike dan filter
        result_data = calculate_freq_spike_and_filter(freq_data, len(cache_files))
        
        # Hapus freq_data setelah selesai
        freq_data.clear()
        
        return result_data
        
    except Exception as e:
        print(f"Error dalam analyze_frequency_spike: {e}")
        return []
    finally:
        # Pastikan freq_data dihapus
        freq_data.clear()

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

def collect_frequency_data_from_cache(cache_dir, cache_files):
    """Kumpulkan data frekuensi dari file cache JSON"""
    freq_data = {}  # {stock_code: [(freq, chg), (freq, chg), ...]}
    
    try:
        for i, file in enumerate(cache_files):
            try:
                file_path = os.path.join(cache_dir, file)
                
                # Baca file JSON
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Ambil data kode saham dan frekuensi
                if 'kode_saham' in data and 'frekuensi' in data and 'selisih' in data:
                    stock_codes = data['kode_saham']
                    frequencies = data['frekuensi']
                    changes = data['selisih']
                    
                    for j, (code, freq, chg) in enumerate(zip(stock_codes, frequencies, changes)):
                        # Skip header row
                        if j == 0 or code == 'KODE SAHAM':
                            continue
                            
                        if code and freq is not None and chg is not None:
                            code = str(code).strip().upper()
                            try:
                                freq = float(freq)
                                chg = float(chg)
                                if freq > 0:  # Hanya ambil frekuensi positif
                                    if code not in freq_data:
                                        freq_data[code] = []
                                    # Simpan tuple (frequency, change)
                                    freq_data[code].append((freq, chg))
                            except:
                                continue
                
                print(f"File {i+1}/{len(cache_files)}: {file} - processed")
                
            except Exception as e:
                print(f"Error membaca file {file}: {e}")
                continue
        
        return freq_data
        
    except Exception as e:
        print(f"Error dalam collect_frequency_data_from_cache: {e}")
        return {}

def calculate_freq_spike_and_filter(freq_data, total_files):
    """Hitung frequency spike dan filter data"""
    result_data = []
    
    for stock_code, data_list in freq_data.items():
        try:
            # Harus ada minimal 14 data untuk bisa dihitung
            if len(data_list) < 14:
                continue
            
            # Data hari ini (data pertama karena file diurutkan terbaru dulu)
            freq_today, chg_today = data_list[0]
            
            # Extract frequencies only
            frequencies = [f for f, c in data_list]
            
            # Rata-rata 7 hari (7 data terbaru)
            avg_7_days = sum(frequencies[:7]) / 7
            
            # Rata-rata 14 hari
            avg_14_days = sum(frequencies[:14]) / 14
            
            # Rata-rata 60 hari (atau semua data yang ada jika < 60)
            max_days = min(len(frequencies), 60)
            avg_60_days = sum(frequencies[:max_days]) / max_days
            
            # Filter: Avg 7hr > Avg 60hr AND Freq hari ini > Avg 7hr
            if avg_7_days > avg_60_days and freq_today > avg_7_days:
                # Hitung spike
                # spike_today vs avg_7_days
                spike_today_vs_7 = freq_today / avg_7_days if avg_7_days > 0 else 0
                
                # spike_7_days vs avg_14_days
                spike_7_vs_14 = avg_7_days / avg_14_days if avg_14_days > 0 else 0
                
                # FSA = (Spike today vs 7 + Spike 7 vs 14) / 2
                fsa = (spike_today_vs_7 + spike_7_vs_14) / 2
                
                result_data.append((stock_code, chg_today, freq_today, avg_60_days, fsa))
        
        except Exception as e:
            print(f"Error processing {stock_code}: {e}")
            continue
    
    # Sort berdasarkan FSA tertinggi
    result_data.sort(key=lambda x: x[4], reverse=True)
    
    return result_data
