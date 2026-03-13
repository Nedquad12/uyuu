from imporh import *
from datetime import datetime, timedelta
import asyncio
from typing import Dict, List, Tuple, Optional

# ==================== CACHE SYSTEM ====================
class MACache:
    """Cache system untuk MA analysis data"""
    
    def __init__(self):
        self.cache: Dict[int, Dict] = {}  # {ma_period: {'data': results, 'timestamp': datetime}}
        self.is_loading: Dict[int, bool] = {}  # Track loading status per MA period
        self.last_reload_time: Optional[datetime] = None
        self.reload_interval = 35 * 60  # 35 menit dalam detik
        self.reload_task: Optional[asyncio.Task] = None
        
    def get(self, ma_period: int) -> Optional[List[Tuple[str, Dict]]]:
        """Ambil data dari cache jika masih valid"""
        if ma_period not in self.cache:
            return None
            
        cache_data = self.cache[ma_period]
        cache_time = cache_data['timestamp']
        
        # Cache valid untuk 35 menit
        if datetime.now() - cache_time < timedelta(seconds=self.reload_interval):
            print(f"âœ… Cache HIT untuk MA {ma_period}")
            return cache_data['data']
        
        print(f"â°ï¸ Cache EXPIRED untuk MA {ma_period}")
        return None
    
    def set(self, ma_period: int, data: List[Tuple[str, Dict]]):
        """Simpan data ke cache"""
        self.cache[ma_period] = {
            'data': data,
            'timestamp': datetime.now()
        }
        print(f"ðŸ'¾ Data MA {ma_period} disimpan ke cache")
    
    def is_period_loading(self, ma_period: int) -> bool:
        """Check apakah MA period sedang loading"""
        return self.is_loading.get(ma_period, False)
    
    def set_loading(self, ma_period: int, status: bool):
        """Set loading status untuk MA period"""
        self.is_loading[ma_period] = status
    
    def clear_all(self):
        """Clear semua cache"""
        self.cache.clear()
        print("ðŸ—'ï¸ Cache MA dibersihkan")
    
    def get_cache_info(self) -> str:
        """Get informasi cache untuk monitoring"""
        if not self.cache:
            return "Cache kosong"
        
        info_lines = []
        for ma_period, cache_data in self.cache.items():
            cache_time = cache_data['timestamp']
            age = (datetime.now() - cache_time).seconds // 60
            data_count = len(cache_data['data'])
            info_lines.append(f"MA {ma_period}: {data_count} coins, {age} menit yang lalu")
        
        return "\n".join(info_lines)

# Global cache instance
ma_cache = MACache()

# ==================== AUTO RELOAD SYSTEM ====================
async def auto_reload_cache():
    """Background task untuk reload cache otomatis setiap 35 menit"""
    
    # Initial delay 30 detik setelah start
    print("â° Waiting 30 seconds before initial cache load...")
    await asyncio.sleep(30)
    
    print("ðŸš€ Starting initial cache load for all MA periods...")
    
    # Initial load untuk semua MA periods
    ma_periods = [20, 60, 100, 200, 400]
    for ma_period in ma_periods:
        try:
            print(f"ðŸ"„ Initial loading MA {ma_period}...")
            result = await analyze_crypto_ma(ma_period)
            if result:
                ma_cache.set(ma_period, result)
                print(f"âœ… MA {ma_period} initial load completed: {len(result)} coins")
            await asyncio.sleep(5)  # Delay 5 detik antar MA period
        except Exception as e:
            print(f"âŒ Error initial loading MA {ma_period}: {e}")
    
    print("âœ… Initial cache load completed!")
    
    # Loop reload setiap 35 menit
    while True:
        try:
            # Wait 35 menit
            await asyncio.sleep(35 * 60)
            
            print(f"\nðŸ"„ Auto-reload cache dimulai - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Reload semua MA periods
            for ma_period in ma_periods:
                try:
                    print(f"ðŸ"„ Reloading MA {ma_period}...")
                    result = await analyze_crypto_ma(ma_period)
                    if result:
                        ma_cache.set(ma_period, result)
                        print(f"âœ… MA {ma_period} reloaded: {len(result)} coins")
                    await asyncio.sleep(5)  # Delay antar reload
                except Exception as e:
                    print(f"âŒ Error reloading MA {ma_period}: {e}")
            
            ma_cache.last_reload_time = datetime.now()
            print(f"âœ… Auto-reload cache selesai - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except asyncio.CancelledError:
            print("ðŸ›' Auto-reload task cancelled")
            break
        except Exception as e:
            print(f"âŒ Error dalam auto-reload: {e}")
            await asyncio.sleep(60)  # Retry setelah 1 menit jika error

def start_ma_cache_reload(application):
    """Start background task untuk auto reload cache"""
    if ma_cache.reload_task is None or ma_cache.reload_task.done():
        ma_cache.reload_task = asyncio.create_task(auto_reload_cache())
        print("âœ… MA cache auto-reload task started")
    else:
        print("â„¹ï¸ MA cache auto-reload task already running")

async def stop_ma_cache_reload():
    """Stop background task untuk auto reload cache"""
    if ma_cache.reload_task and not ma_cache.reload_task.done():
        ma_cache.reload_task.cancel()
        try:
            await ma_cache.reload_task
        except asyncio.CancelledError:
            pass
        print("âœ… MA cache auto-reload task stopped")

# ==================== TELEGRAM COMMANDS ====================
@is_authorized_user 
@spy      
@vip       
async def ma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk analisis Moving Average cryptocurrency"""
    
    try:
        # Buat inline keyboard untuk pilihan MA dengan tambahan MA 60 dan MA 400
        keyboard = [
            [InlineKeyboardButton("MA 20", callback_data="ma_20"), InlineKeyboardButton("MA 60", callback_data="ma_60")],
            [InlineKeyboardButton("MA 100", callback_data="ma_100"), InlineKeyboardButton("MA 200", callback_data="ma_200")],
            [InlineKeyboardButton("MA 400", callback_data="ma_400")],
            [InlineKeyboardButton("ðŸ"„ Reload Cache", callback_data="ma_reload"), InlineKeyboardButton("ðŸ"Š Cache Info", callback_data="ma_cache_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "ðŸ"ˆ Pilih periode Moving Average yang ingin dianalisis:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logging.error(f"Error dalam ma_command: {e}")
        await update.message.reply_text(f"âŒ Terjadi error: {str(e)}")

async def ma_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk callback dari inline keyboard MA"""
    
    query = update.callback_query
    await query.answer()
    
    try:
        # Handle cache info command
        if query.data == "ma_cache_info":
            cache_info = ma_cache.get_cache_info()
            last_reload = ma_cache.last_reload_time.strftime('%Y-%m-%d %H:%M:%S') if ma_cache.last_reload_time else "Belum pernah reload"
            
            info_message = f"""
ðŸ"Š **MA Cache Information**

**Cache Status:**
{cache_info}

**Last Auto-Reload:** {last_reload}
**Reload Interval:** 35 menit
**Auto-Reload:** {'ðŸŸ¢ Active' if ma_cache.reload_task and not ma_cache.reload_task.done() else 'ðŸ"´ Inactive'}

Cache membantu mempercepat loading data MA analysis.
            """
            await query.edit_message_text(info_message, parse_mode='Markdown')
            return
        
        # Handle reload cache command
        if query.data == "ma_reload":
            await query.edit_message_text("ðŸ"„ Memuat ulang semua cache MA... Mohon tunggu...")
            
            ma_periods = [20, 60, 100, 200, 400]
            success_count = 0
            
            for ma_period in ma_periods:
                try:
                    result = await analyze_crypto_ma(ma_period)
                    if result:
                        ma_cache.set(ma_period, result)
                        success_count += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"Error reloading MA {ma_period}: {e}")
            
            await query.edit_message_text(
                f"âœ… Cache reload selesai!\n"
                f"Berhasil: {success_count}/{len(ma_periods)} MA periods\n"
                f"Gunakan /ma untuk analisis."
            )
            return
        
        # Hapus keyboard dan tampilkan loading message
        await query.edit_message_text("ðŸ"¥ Menganalisis Moving Average... Mohon tunggu sebentar...")
        
        # Extract MA period from callback data
        ma_period = int(query.data.split('_')[1])
        
        # Check cache first
        result_data = ma_cache.get(ma_period)
        
        if result_data is None:
            # Cache miss - check if already loading
            if ma_cache.is_period_loading(ma_period):
                await query.edit_message_text(
                    f"â° MA {ma_period} sedang dimuat oleh request lain. Mohon tunggu sebentar..."
                )
                # Wait maksimal 60 detik untuk loading selesai
                for _ in range(60):
                    await asyncio.sleep(1)
                    result_data = ma_cache.get(ma_period)
                    if result_data is not None:
                        break
                
                if result_data is None:
                    await query.edit_message_text("âŒ Timeout menunggu data. Silakan coba lagi.")
                    return
            else:
                # Set loading status
                ma_cache.set_loading(ma_period, True)
                
                try:
                    # Load fresh data
                    await query.edit_message_text(f"ðŸ"¥ Memuat data MA {ma_period} (fresh load)...")
                    result_data = await analyze_crypto_ma(ma_period)
                    
                    if result_data:
                        ma_cache.set(ma_period, result_data)
                finally:
                    ma_cache.set_loading(ma_period, False)
        else:
            await query.edit_message_text(f"âš¡ Menggunakan cached data MA {ma_period}...")
        
        if not result_data:
            await query.edit_message_text("âŒ Tidak ada data yang memenuhi kriteria atau terjadi error saat memproses data")
            return
        
        # Format header
        cache_indicator = "ðŸ'¾ [Cached]" if ma_cache.get(ma_period) is not None else "ðŸ†• [Fresh]"
        header_message = f"ðŸ"ˆ **Crypto Near MA {ma_period} Analysis** {cache_indicator}\n\n"
        header_message += f"Total crypto dalam jarak 0.7% dari MA {ma_period} ada: {len(result_data)} koin\n\n"
        
        await query.edit_message_text(header_message, parse_mode='Markdown')
        
        # Format data dengan informasi lengkap
        data_lines = []
        data_lines.append(f"Symbol       Price     MA-{ma_period}     Distance   Vol-24h     VSA")
        data_lines.append("─" * 70)
        
        for symbol, data in result_data:
            price = data['current_price']
            ma_value = data['ma_value']
            distance = data['distance_percent']
            vol_24h = data['vol_24h'] / 1_000_000  # Dalam juta
            vsa = data.get('vsa', 0)  # VSA dari vol.py jika tersedia
            
            # Format dengan alignment yang rapi
            data_lines.append(f"{symbol:<12} ${price:>8.4f} ${ma_value:>8.4f} {distance:>8.2f}% {vol_24h:>8.1f}M {vsa:>7.2f}")
        
        # Split data ke beberapa message jika terlalu panjang
        max_lines_per_message = 25
        current_message_lines = []
        
        for line in data_lines:
            current_message_lines.append(line)
            
            if len(current_message_lines) >= max_lines_per_message:
                # Kirim message saat ini
                message_content = "```\n" + "\n".join(current_message_lines) + "\n```"
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message_content,
                    parse_mode='Markdown'
                )
                
                # Reset untuk message berikutnya
                current_message_lines = []
        
        # Kirim sisa data jika ada
        if current_message_lines:
            message_content = "```\n" + "\n".join(current_message_lines) + "\n```"
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=message_content,
                parse_mode='Markdown'
            )
        
        # Kirim footer
        footer_message = f"\nðŸ"Š **Keterangan:**\n"
        footer_message += f"• MA-{ma_period}: Moving Average {ma_period} hari\n"
        footer_message += "• Distance: Jarak harga saat ini ke MA (% di atas/bawah)\n"
        footer_message += "• Vol-24h: Volume 24 jam terakhir\n"
        footer_message += "• VSA: Volume Spike Average (jika tersedia)\n"
        footer_message += "• Satuan: M = Juta USDT\n"
        footer_message += "• Hanya menampilkan crypto dalam jarak ±0.7% dari MA"
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=footer_message,
            parse_mode='Markdown'
        )
            
    except Exception as e:
        logging.error(f"Error dalam ma_callback_handler: {e}")
        await query.edit_message_text(f"âŒ Terjadi error: {str(e)}")
    finally:
        # Force garbage collection
        gc.collect()

# ==================== MA ANALYSIS FUNCTIONS ====================
async def analyze_crypto_ma(ma_period: int) -> List[Tuple[str, Dict]]:
    """Fungsi utama untuk analisis Moving Average cryptocurrency"""
    
    try:
        # Step 1: Ambil semua USDT pairs
        print("Mengambil daftar USDT pairs...")
        usdt_pairs = await get_usdt_pairs_ma()
        
        if not usdt_pairs:
            print("Tidak ada USDT pairs yang ditemukan")
            return []
        
        print(f"Ditemukan {len(usdt_pairs)} USDT pairs")
        
        # Step 2: Ambil data historical untuk setiap pair
        print(f"Mengambil data historical untuk MA {ma_period}...")
        ma_results = await get_ma_data_batch(usdt_pairs, ma_period)
        
        if not ma_results:
            print("Tidak ada data MA yang berhasil dikumpulkan")
            return []
        
        # Step 3: Filter berdasarkan jarak ke MA
        print("Filtering berdasarkan jarak ke MA...")
        filtered_results = filter_ma_distance(ma_results)
        
        # Step 4: Tambahkan data VSA jika tersedia (dari vol.py logic)
        print("Menambahkan data VSA...")
        enriched_results = await enrich_with_vsa_data(filtered_results)
        
        print(f"Hasil akhir: {len(enriched_results)} crypto memenuhi kriteria")
        return enriched_results
        
    except Exception as e:
        print(f"Error dalam analyze_crypto_ma: {e}")
        return []

async def get_usdt_pairs_ma() -> List[str]:
    """Ambil semua pasangan USDT dari Binance untuk MA analysis"""
    
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.binance.com/api/v3/exchangeInfo"
            
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Error getting exchange info: {response.status}")
                    return []
                
                data = await response.json()
                
                # Filter hanya USDT pairs yang aktif
                usdt_pairs = []
                for symbol_info in data['symbols']:
                    symbol = symbol_info['symbol']
                    if (symbol.endswith('USDT') and 
                        symbol_info['status'] == 'TRADING' and
                        symbol_info['quoteAsset'] == 'USDT'):
                        usdt_pairs.append(symbol)
                
                return usdt_pairs
                
    except Exception as e:
        print(f"Error dalam get_usdt_pairs_ma: {e}")
        return []

async def get_ma_data_batch(symbols: List[str], ma_period: int) -> Dict[str, Dict]:
    """Ambil data historical untuk batch symbols secara async"""
    
    ma_data = {}
    
    # Batasi concurrent requests untuk menghindari rate limit
    semaphore = asyncio.Semaphore(8)  # Max 8 concurrent requests
    
    async def get_single_ma_data(session, symbol):
        async with semaphore:
            try:
                # Ambil data dengan buffer yang cukup untuk MA period yang besar
                # Untuk MA 400, butuh minimal 410 hari data
                data_limit = max(500, ma_period + 20)  # Minimal 500 atau MA period + buffer
                
                url = "https://api.binance.com/api/v3/klines"
                params = {
                    'symbol': symbol,
                    'interval': '1d',  # Daily data
                    'limit': min(1000, data_limit)  # Max 1000 limit dari Binance API
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        klines = await response.json()
                        
                        if len(klines) >= ma_period + 1:
                            # Extract close prices dan volumes
                            closes = []
                            volumes = []
                            for kline in klines:
                                close_price = float(kline[4])  # Close price index 4
                                volume = float(kline[5])       # Volume index 5
                                closes.append(close_price)
                                volumes.append(volume)
                            
                            # Reverse supaya data terbaru di depan
                            closes.reverse()
                            volumes.reverse()
                            
                            # Hitung MA
                            current_price = closes[0]  # Harga saat ini
                            ma_value = sum(closes[1:ma_period+1]) / ma_period  # MA dari data sebelumnya
                            
                            # Hitung jarak ke MA dalam persen
                            distance_percent = ((current_price - ma_value) / ma_value) * 100
                            
                            ma_data[symbol] = {
                                'current_price': current_price,
                                'ma_value': ma_value,
                                'distance_percent': distance_percent,
                                'vol_24h': volumes[0],  # Volume 24h terakhir
                                'volumes': volumes  # Simpan untuk VSA calculation
                            }
                            
                            print(f"✅ {symbol}: MA{ma_period}=${ma_value:.4f}, Distance={distance_percent:.2f}%")
                        else:
                            print(f"❌ {symbol}: Data tidak cukup ({len(klines)} hari, butuh {ma_period+1})")
                    else:
                        print(f"❌ {symbol}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"❌ {symbol}: Error - {e}")
            
            # Rate limiting delay - lebih lama untuk MA period yang besar
            delay = 0.15 if ma_period <= 200 else 0.25
            await asyncio.sleep(delay)
    
    try:
        async with aiohttp.ClientSession() as session:
            # Buat semua tasks
            tasks = [get_single_ma_data(session, symbol) for symbol in symbols]
            
            # Jalankan dalam batch untuk menghindari terlalu banyak concurrent requests
            # Batch size lebih kecil untuk MA period yang besar
            batch_size = 30 if ma_period <= 200 else 20
            
            for i in range(0, len(tasks), batch_size):
                batch_tasks = tasks[i:i + batch_size]
                await asyncio.gather(*batch_tasks, return_exceptions=True)
                print(f"Batch {i//batch_size + 1} selesai...")
                
                # Delay antar batch lebih lama untuk MA period besar
                delay = 2 if ma_period <= 200 else 3
                await asyncio.sleep(delay)
        
        return ma_data
        
    except Exception as e:
        print(f"Error dalam get_ma_data_batch: {e}")
        return {}

def filter_ma_distance(ma_data: Dict[str, Dict]) -> List[Tuple[str, Dict]]:
    """Filter crypto berdasarkan jarak ke MA (maksimal 0.7%)"""
    
    filtered_results = []
    
    for symbol, data in ma_data.items():
        try:
            distance_percent = abs(data['distance_percent'])
            
            # Filter: jarak ke MA maksimal 0.7%
            if distance_percent <= 0.7:
                filtered_results.append((symbol, data))
                
        except Exception as e:
            print(f"Error filtering {symbol}: {e}")
            continue
    
    # Sort berdasarkan jarak terdekat ke MA
    filtered_results.sort(key=lambda x: abs(x[1]['distance_percent']))
    
    return filtered_results

async def enrich_with_vsa_data(ma_results: List[Tuple[str, Dict]]) -> List[Tuple[str, Dict]]:
    """Enrich data MA dengan VSA calculation dari vol.py logic"""
    
    enriched_results = []
    
    for symbol, data in ma_results:
        try:
            volumes = data.get('volumes', [])
            
            if len(volumes) >= 8:  # Minimal 8 hari untuk VSA calculation
                # Ambil logic VSA dari vol.py
                vol_yesterday = volumes[1] if len(volumes) > 1 else volumes[0]
                
                # Rata-rata periode
                avg_7d = sum(volumes[1:8]) / 7 if len(volumes) >= 8 else sum(volumes[1:]) / max(1, len(volumes)-1)
                avg_30d = sum(volumes[1:31]) / min(30, len(volumes)-1) if len(volumes) > 30 else sum(volumes[1:]) / max(1, len(volumes)-1)
                avg_60d = sum(volumes[1:61]) / min(60, len(volumes)-1) if len(volumes) > 60 else sum(volumes[1:]) / max(1, len(volumes)-1)
                
                # Hitung VSA components
                spike_yesterday = vol_yesterday / avg_7d if avg_7d > 0 else 0
                spike_7vs30 = avg_7d / avg_30d if avg_30d > 0 else 0
                spike_7vs60 = avg_7d / avg_60d if avg_60d > 0 else 0
                
                # VSA = (spike_yesterday + spike_7vs30 + spike_7vs60) / 3
                vsa = (spike_yesterday + spike_7vs30 + spike_7vs60) / 3
                
                # Tambahkan VSA ke data
                data['vsa'] = vsa
                data['vol_yesterday'] = vol_yesterday
                data['avg_7d'] = avg_7d
            else:
                data['vsa'] = 0
            
            enriched_results.append((symbol, data))
            
        except Exception as e:
            print(f"Error enriching VSA for {symbol}: {e}")
            # Tetap tambahkan tanpa VSA
            data['vsa'] = 0
            enriched_results.append((symbol, data))
    
    # Sort berdasarkan VSA tertinggi, kemudian jarak MA terdekat
    enriched_results.sort(key=lambda x: (-x[1]['vsa'], abs(x[1]['distance_percent'])))
    
    return enriched_results

# Handler untuk callback query (perlu didaftarkan di main.py)
def get_ma_callback_handler():
    """Return callback handler untuk MA commands"""
    return CallbackQueryHandler(ma_callback_handler, pattern="^ma_")

# Utility function untuk testing
async def test_crypto_ma(ma_period: int = 20):
    """Function untuk testing tanpa telegram bot"""
    result = await analyze_crypto_ma(ma_period)
    
    if result:
        print(f"\nðŸ"ˆ CRYPTO NEAR MA {ma_period} (Distance <= 0.7%):")
        print("=" * 80)
        print(f"{'Symbol':<12} {'Price':<12} {f'MA-{ma_period}':<12} {'Distance':<10} {'Vol-24h':<12} {'VSA':<8}")
        print("-" * 80)
        
        for symbol, data in result[:20]:  # Top 20
            price = data['current_price']
            ma_value = data['ma_value']
            distance = data['distance_percent']
            vol_24h = data['vol_24h'] / 1_000_000
            vsa = data.get('vsa', 0)
            
            print(f"{symbol:<12} ${price:>8.4f} ${ma_value:>8.4f} {distance:>8.2f}% {vol_24h:>8.1f}M {vsa:>7.2f}")
    else:
        print("Tidak ada hasil")

# Jalankan test jika file dijalankan langsung
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ma_period = int(sys.argv[1])
        asyncio.run(test_crypto_ma(ma_period))
    else:
        # Default test
        asyncio.run(test_crypto_ma(20))