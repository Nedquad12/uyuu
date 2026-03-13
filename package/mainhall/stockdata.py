import sys
sys.path.append ("/home/ec2-user/package/machine")
from utama import TelegramStockDataViewer
from imporh import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_as_code_block(text: str) -> str:
    return f"```\n{text.strip()}\n```"

viewer = TelegramStockDataViewer()

@is_authorized_user 
@spy      
@vip       
@with_queue_control  
async def show_indices_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if not is_authorized_user(update):
        await update.message.reply_text(
            "Hi!! Maaf kamu tidak terdaftar sebagai member premium." "Jika ingin  bergabung menjadi member premium dan menggunakan bot sesuka hati bisa hubungi @Rendanggedang"
        )
        return

    try:
        indices = {
            'ES=F': 'USA',
            'BTC-USD': 'Bitcoin',
            '^NZ50': 'N.Zealand',
            '^AXJO': 'Australia',
            '^N225': 'Jepang',
            '^KS11': 'Korea',
            '^STI': 'Singapore',
            '000001.SS': 'China',
            '^HSI': 'Hong Kong',
            '^KLSE': 'Malaysia',
            '^TWII': 'Taiwan',
            '^JKSE': 'Indonesia',
            '^BSESN': 'India'
        }

        currencies = {
            'IDR=X': 'USD/IDR',
            'JPY=X': 'USD/JPY',
            'AUDUSD=X': 'AUD/USD',
            'EURUSD=X': 'EUR/USD',
            'GBPUSD=X': 'GBP/USD',
            'THB=X': 'USD/THB',
            'MYR=X': 'USD/MYR'
        }

        commodities = {
            'GC=F': 'Gold',
            'SI=F': 'Silver',
            'PL=F': 'Platinum',
            'CL=F': 'Crude Oil',
            'HG=F': 'Copper',
            'NG=F': 'Natural Gas'
        }

        response = "📊 *Data Index, Currency and Commodities.*\n\n"

        def fetch_data(tickers, category_name):
            lines = [f"📌 *{category_name}*"]
            for ticker, name in tickers.items():
                try:
                    data = yf.Ticker(ticker)
                    price = data.history(period="1d", interval="1m")['Close'].iloc[-1]
                    prev_close = data.history(period="2d")['Close'].iloc[-2]
                    change = price - prev_close
                    pct_change = (change / prev_close) * 100

                    if change > 0:
                        arrow = "🟢"
                    elif change < 0:
                        arrow = "🔴"
                    else:
                        arrow = "⚪"

                    lines.append(f"{name}: {price:,.2f} {arrow} {change:+.2f} ({pct_change:+.2f}%)")
                except Exception as e:
                    lines.append(f"{name}: ❌ Error")
            return "\n".join(lines)

        response += fetch_data(indices, "Indices")
        response += "\n\n" + fetch_data(currencies, "Currencies")
        response += "\n\n" + fetch_data(commodities, "Commodities")

        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching market data: {str(e)}")

@is_authorized_user  
@spy          
@with_queue_control          
async def free_float_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    try:
        folder_path = "/home/ec2-user/database/foreign"
        excel_files = sorted(glob.glob(os.path.join(folder_path, "*.xlsx")), reverse=True)
        if not excel_files:
            await update.message.reply_text( f"❌ Server error `{folder_path}`.")
            return

        latest_file = excel_files[0]
        df = pd.read_excel(latest_file)

        required_cols = ['Kode Saham', 'Weight For Index', 'Penutupan', 'Listed Shares']
        if not all(col in df.columns for col in required_cols):
            await update.message.reply_text( f"❌ Kolom {required_cols} tidak ditemukan di database.")
            return

        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text( "❌ Masukan kode saham.\nContoh: `/ff BBCA`", parse_mode='Markdown')
            return
        

        code = parts[1].upper()
        stock = df[df['Kode Saham'].str.upper() == code]

        if stock.empty:
            await update.message.reply_text( f"❌ Saham {code} tidak ditemukan.")
            return

        weight_index = stock['Weight For Index'].values[0]
        penutupan = stock['Penutupan'].values[0]
        listed_shares = stock['Listed Shares'].values[0]

        # Hitung Free Float Value
        ff_value = weight_index * penutupan
        ff_percent = (weight_index / listed_shares) * 100

        # Format nilai
        def format_value(val):
            if val >= 1e12:
                return f"{val/1e12:.0f}T"
            elif val >= 1e9:
                return f"{val/1e9:.1f}B"
            elif val >= 1e6:
                return f"{val/1e6:.1f}M"
            else:
                return f"{val:.0f}"
            
        def format_with_dot(val):
            return f"{int(val):,}".replace(",", ".")

        ff_value_str = format_value(ff_value)
        weight_index_str = format_with_dot(weight_index)

        # Bandingkan dengan MSCI
        kurs = 16300
        min_value_15 = 6000e9  # Rp5500B
        min_value_low_ff = 8400e12  # Rp8400T

        meets_value = ff_value * kurs >= min_value_15
        meets_ff = ff_percent >= 15

        if meets_ff and meets_value:
            status = "✅ Memenuhi syarat MSCI (Rp5500B, FF≥15%)"
        elif not meets_ff and ff_value * kurs >= min_value_low_ff:
            status = "⚠️ Potensi eligible."
        else:
            status = "❌ Belum memenuhi syarat MSCI"

        response = (
            f"📊 Free Float Summary for {code}\n"
            f"💰 FFMC: {ff_value_str}\n"
            f"📈 Free Float: {ff_percent:.2f}%\n"
            f"📊 free Float: {weight_index_str} lembar\n"
            f""
        )
        await update.message.reply_text( response)

    except Exception as e:
        await update.message.reply_text( f"❌ Error: {str(e)}")
        logger.error(f"Error in /ff command: {e}")
            
@is_authorized_user
@spy
@with_queue_control
async def valuation_dual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        if len(parts) != 5:
            await update.message.reply_text(
                "❌ Format salah.\n\nContoh:\n`/val 2500 1.1 125 25`\n(BVPS, PBV, EPS, PER)", parse_mode='Markdown')
            return

        _, bvps, pbv, eps, per = parts

        try:
            bvps = float(bvps)
            pbv = float(pbv)
            eps = float(eps)
            per = float(per)
        except ValueError:
            await update.message.reply_text("❌ Semua nilai harus berupa angka.\nContoh: `/val 2500 1.1 125 25`", parse_mode='Markdown')
            return

        # Validasi input - hapus validasi PER > 0 karena sekarang bisa negatif
        if pbv <= 0:
            await update.message.reply_text("❌ PBV harus lebih besar dari 0.", parse_mode='Markdown')
            return

        harga_pbv = bvps * pbv

        # Format
        f = lambda x: f"{x:,.0f}".replace(",", ".")
        f2 = lambda x: f"{x:.2f}"

        response = (
            f"📘 *Estimasi Harga Berdasarkan PBV*\n"
            f"📦 BVPS: {f(bvps)}\n"
            f"📊 Target PBV: {f2(pbv)}\n"
            f"💰 Harga: *{f(harga_pbv)}*\n\n"
        )

        # Logika baru untuk perhitungan PER
        if eps < 0 and per < 0:
            # Jika keduanya negatif: (-EPS) * (-PER) = positif
            harga_per = abs(eps) * abs(per)
            response += (
                f"📗 *Estimasi Harga Berdasarkan PER*\n"
                f"📈 EPS: {f(eps)} (negatif)\n"
                f"📊 Target PER: {f2(per)} (negatif)\n"
                f"💰 Harga: *{f(harga_per)}*\n"
                f"ℹ️ *PER dan EPS minus, hati-hati*"
            )
        elif eps < 0:
            # Hanya EPS negatif
            harga_per = abs(eps) * per
            response += (
                f"📗 *Estimasi Harga Berdasarkan PER*\n"
                f"📈 EPS: {f(eps)} (negatif)\n"
                f"📊 Target PER: {f2(per)}\n"
                f"💰 Harga: *{f(harga_per)}*\n"
                f"ℹ️ *EPS Negatif, hati-hati*"
            )
        elif per < 0:
            # Hanya PER negatif
            harga_per = eps * abs(per)
            response += (
                f"📗 *Estimasi Harga Berdasarkan PER*\n"
                f"📈 EPS: {f(eps)}\n"
                f"📊 Target PER: {f2(per)} (negatif)\n"
                f"💰 Harga: *{f(harga_per)}*\n"
                f"ℹ️ *Dihitung dengan EPS × |PER|*"
            )
        else:
            # Keduanya positif (normal)
            harga_per = eps * per
            response += (
                f"📗 *Estimasi Harga Berdasarkan PER*\n"
                f"📈 EPS: {f(eps)}\n"
                f"📊 Target PER: {f2(per)}\n"
                f"💰 Harga: *{f(harga_per)}*"
            )

        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")