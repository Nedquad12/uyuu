from telegram import Update
from telegram.ext import ContextTypes
import logging
import os
import matplotlib.pyplot as plt
import gc
import glob
import pandas as pd
from datetime import datetime
import io
from admin.auth import is_authorized_user, is_vip_user, check_public_group_access
from admin.admin_command import active_admins

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Folder data Listed Shares (sama dengan /ff) ────────────────────────────────
FF_FOLDER = "/home/ec2-user/database/foreign"


def get_listed_shares(ticker: str) -> float | None:
    """
    Ambil Listed Shares untuk ticker dari file foreign (sama sumber dengan /ff).
    Return float atau None jika tidak ditemukan.
    """
    excel_files = sorted(glob.glob(os.path.join(FF_FOLDER, "*.xlsx")), reverse=True)
    if not excel_files:
        return None
    try:
        df = pd.read_excel(excel_files[0])
        if 'Kode Saham' not in df.columns or 'Listed Shares' not in df.columns:
            return None
        row = df[df['Kode Saham'].str.upper() == ticker.upper()]
        if row.empty:
            return None
        val = float(row.iloc[0]['Listed Shares'])
        return val if val > 0 else None
    except Exception as e:
        logger.error(f"[get_listed_shares] Error: {e}")
        return None


class Blackrock:
    def __init__(self, data_folder=None):
        print("✅ Utama siap digunakan")

        self.company_names = {
            'indonesia': 'BlackRock Indonesia',
            'spdr':      'SPDR',
        }

        self.blackrock_folders = {
            'indonesia': "/home/ec2-user/database/br/ind",
            'spdr':      "/home/ec2-user/database/br/spdr",
        }

        self.combined_df   = None
        self.user_data     = {}

        self.blackrock_data = {
            'indonesia': None,
            'spdr':      None,
        }

        self.watchlist_data     = None
        self.watchlist_averages = None

    # ── Loader semua region ────────────────────────────────────────────────────

    def load_blackrock_data(self):
        for region, folder_path in self.blackrock_folders.items():
            try:
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)
                    continue

                excel_files = []
                for extension in ['*.xlsx', '*.xls']:
                    excel_files.extend(glob.glob(os.path.join(folder_path, extension)))

                if not excel_files:
                    continue

                excel_files = sorted(excel_files, reverse=True)[:60]

                dataframes = []
                for file_path in excel_files:
                    try:
                        filename = os.path.basename(file_path)
                        date_str = filename.split('.')[0]

                        df = pd.read_excel(file_path)

                        if len(date_str) == 6:
                            day   = int(date_str[:2])
                            month = int(date_str[2:4])
                            year  = int('20' + date_str[4:6])
                            file_date = datetime(year, month, day)
                            df['Date'] = file_date

                        dataframes.append(df)

                    except Exception as e:
                        logger.error(f"❌ Error loading file {file_path}: {e}")
                        continue

                if dataframes:
                    self.blackrock_data[region] = pd.concat(dataframes, ignore_index=True)
                    self.blackrock_data[region] = self.blackrock_data[region].sort_values('Date', ascending=True)

            except Exception as e:
                logger.error(f"❌ Error loading data for {region}: {e}")

    # ── Loader per region ──────────────────────────────────────────────────────

    def load_blackrock_data_for_region(self, region):
        folder_path = self.blackrock_folders.get(region)
        if not folder_path or not os.path.exists(folder_path):
            self.blackrock_data[region] = None
            return

        excel_files = []
        for extension in ['*.xlsx', '*.xls']:
            excel_files.extend(glob.glob(os.path.join(folder_path, extension)))

        if not excel_files:
            self.blackrock_data[region] = None
            return

        excel_files = sorted(excel_files, reverse=True)[:60]

        dataframes = []
        for file_path in excel_files:
            try:
                df = pd.read_excel(file_path)
                filename  = os.path.basename(file_path)
                date_str  = filename.split('.')[0]
                if len(date_str) == 6:
                    day   = int(date_str[:2])
                    month = int(date_str[2:4])
                    year  = int('20' + date_str[4:6])
                    file_date = datetime(year, month, day)
                    df['Date'] = file_date
                dataframes.append(df)
            except Exception as e:
                logger.error(f"❌ Error loading file {file_path}: {e}")
                continue

        if dataframes:
            self.blackrock_data[region] = pd.concat(dataframes, ignore_index=True)
            self.blackrock_data[region] = self.blackrock_data[region].sort_values('Date', ascending=True)
        else:
            self.blackrock_data[region] = None

    # ── Search ticker ──────────────────────────────────────────────────────────

    def search_blackrock_ticker(self, region, ticker):
        if region not in self.blackrock_data or self.blackrock_data[region] is None:
            return None

        data = self.blackrock_data[region].copy()
        data['Ticker'] = data['Ticker'].astype(str).fillna('')
        data = data[~data['Ticker'].isin(['', 'nan', 'None'])]
        ticker_data = data[data['Ticker'].str.upper() == str(ticker).upper()]

        return ticker_data if not ticker_data.empty else None

    # ── Helper: ambil kolom qty berdasarkan region ─────────────────────────────

    def _qty_col(self, region: str) -> str:
        """Kolom quantity yang dipakai sebagai acuan per region."""
        if region == 'spdr':
            return 'Grand Total'
        return 'Quantity Total'

    # ── Chart BlackRock / SPDR ─────────────────────────────────────────────────

    def create_blackrock_chart(self, region, ticker):
        ticker_data = self.search_blackrock_ticker(region, ticker)
        if ticker_data is None:
            return None, None

        qty_col = self._qty_col(region)
        grouped = ticker_data.groupby('Date').last().sort_index()

        # Ambil Listed Shares untuk % kepemilikan
        listed_shares = get_listed_shares(ticker)  # masih dipakai oleh caption
        fig, ax1 = plt.subplots(figsize=(12, 6))
        ax2 = None
        
        ax1.plot(grouped.index, grouped[qty_col], marker='o', linewidth=2, color='blue')
        company_name = self.company_names.get(region, 'BlackRock')
        ax1.set_title(f'{company_name} Holdings - {ticker}', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Date', fontsize=11)
        ax1.set_ylabel(qty_col, fontsize=11)
        ax1.grid(True, alpha=0.3)

        # Watermark
        fig.text(0.5, 0.5, 'Membahas Saham Indonesia', fontsize=50, color='gray',
                 ha='center', va='center', alpha=0.15, rotation=30, zorder=10)

        plt.tight_layout()

        chart_buf = io.BytesIO()
        plt.savefig(chart_buf, format='png', dpi=300, bbox_inches='tight')
        chart_buf.seek(0)
        plt.close('all')
        gc.collect()

        caption = self.generate_movement_caption(grouped, ticker, region, listed_shares)

        return chart_buf, caption

    # ── Caption BlackRock / SPDR ───────────────────────────────────────────────

    def generate_movement_caption(self, grouped_data, ticker, region, listed_shares=None):
        qty_col      = self._qty_col(region)
        company_name = self.company_names.get(region, 'BlackRock')

        if len(grouped_data) < 2:
            return (
                f"📊 {company_name} Holdings - {ticker}\n"
                f"❌ Insufficient data for movement analysis"
            )

        latest   = grouped_data.iloc[-1]
        previous = grouped_data.iloc[-2]

        qty_change     = latest[qty_col] - previous[qty_col]
        qty_change_pct = (qty_change / previous[qty_col]) * 100 if previous[qty_col] != 0 else 0

        qty_arrow = "🔺" if qty_change > 0 else "🔻" if qty_change < 0 else "➡️"

        caption = f"📊 {company_name} Holdings - {ticker}\n\n"
        caption += f"📅 Latest  : {latest.name.strftime('%d-%b-%Y')}\n"
        caption += f"📅 Previous: {previous.name.strftime('%d-%b-%Y')}\n\n"
        caption += f"📈 {qty_col}:\n"
        caption += f"   Current : {latest[qty_col]:,.0f}\n"
        caption += f"   Previous: {previous[qty_col]:,.0f}\n"
        caption += f"   Change  : {qty_arrow} {qty_change:+,.0f} ({qty_change_pct:+.2f}%)\n"

        # Market Value — hanya ada di BlackRock (bukan SPDR)
        if region != 'spdr' and 'Market Value Total' in grouped_data.columns:
            mv_change     = latest['Market Value Total'] - previous['Market Value Total']
            mv_change_pct = (mv_change / previous['Market Value Total']) * 100 if previous['Market Value Total'] != 0 else 0
            mv_arrow      = "🔺" if mv_change > 0 else "🔻" if mv_change < 0 else "➡️"
            caption += f"\n💰 Market Value Total:\n"
            caption += f"   Current : ${latest['Market Value Total']:,.0f}\n"
            caption += f"   Previous: ${previous['Market Value Total']:,.0f}\n"
            caption += f"   Change  : {mv_arrow} ${mv_change:+,.0f} ({mv_change_pct:+.2f}%)\n"

        return caption

    # ── Combined summary (tidak berubah) ───────────────────────────────────────

    def create_combined_summary(self, ticker, search_results):
        if not search_results:
            return f"❌ Ticker {ticker} tidak ditemukan di semua Manager Investasi"

        summary      = f"📊 Summary for {ticker}:\n\n"
        total_qty    = 0
        total_mv     = 0
        latest_date  = None

        for region, result in search_results.items():
            company_name     = self.company_names.get(region, 'BlackRock')
            data             = result['data']
            formatted_ticker = result['formatted_ticker']

            grouped = data.groupby('Date').last().sort_index()
            if len(grouped) > 0:
                latest = grouped.iloc[-1]
                qty_col = self._qty_col(region)
                summary += f"🏢 {company_name} ({region.upper()}):\n"
                summary += f"   Ticker: {formatted_ticker}\n"
                summary += f"   Quantity: {latest[qty_col]:,.0f}\n"
                if region != 'spdr' and 'Market Value Total' in latest.index:
                    summary += f"   Market Value: ${latest['Market Value Total']:,.0f}\n"
                summary += f"   Latest Date: {latest.name.strftime('%d-%b-%Y')}\n\n"
                total_qty += latest[qty_col]
                if region != 'spdr' and 'Market Value Total' in latest.index:
                    total_mv += latest['Market Value Total']

                if latest_date is None or latest.name > latest_date:
                    latest_date = latest.name

        summary += f"📊 TOTAL Manager Investment:\n"
        summary += f"   Total Quantity: {total_qty:,.0f}\n"
        if total_mv > 0:
            summary += f"   Total Market Value: ${total_mv:,.0f}\n"
        summary += f"   Latest Update: {latest_date.strftime('%d-%b-%Y') if latest_date else 'N/A'}\n"

        return summary

    # ── Significant movements (BlackRock + SPDR) ──────────────────────────────

    def get_significant_movements(self, threshold=3.0):
        movements = []

        for region, data in self.blackrock_data.items():
            if data is None or len(data) < 2:
                continue

            qty_col   = self._qty_col(region)
            data_copy = data.copy()
            data_copy['Ticker'] = data_copy['Ticker'].astype(str).fillna('')
            data_copy = data_copy[~data_copy['Ticker'].isin(['', 'nan', 'None'])]

            # Pastikan kolom qty ada
            if qty_col not in data_copy.columns:
                logger.warning(f"[b7] Kolom '{qty_col}' tidak ada di region {region}, skip.")
                continue

            latest_dates = sorted(data_copy['Date'].unique(), reverse=True)[:5]
            data_copy    = data_copy[data_copy['Date'].isin(latest_dates)]

            tickers = data_copy['Ticker'].unique()

            for ticker in tickers:
                ticker_data = (
                    data_copy[data_copy['Ticker'] == ticker]
                    .groupby('Date').last()
                    .sort_index()
                )

                if len(ticker_data) < 2:
                    continue

                latest   = ticker_data.iloc[-1]
                previous = ticker_data.iloc[-2]

                if previous[qty_col] == 0:
                    continue

                qty_change_pct = (
                    (latest[qty_col] - previous[qty_col]) / previous[qty_col]
                ) * 100

                if abs(qty_change_pct) >= threshold:
                    entry = {
                        'region':       region,
                        'ticker':       ticker,
                        'change_pct':   qty_change_pct,
                        'latest_qty':   latest[qty_col],
                        'previous_qty': previous[qty_col],
                        'latest_date':  latest.name,
                        'previous_date': previous.name,
                    }
                    # Market Value hanya BlackRock
                    if region != 'spdr' and 'Market Value Total' in latest.index:
                        entry['latest_mv']   = latest['Market Value Total']
                        entry['previous_mv'] = previous['Market Value Total']
                    else:
                        entry['latest_mv']   = 0
                        entry['previous_mv'] = 0

                    movements.append(entry)

        movements.sort(key=lambda x: abs(x['change_pct']), reverse=True)
        return movements


# ── Singleton ──────────────────────────────────────────────────────────────────
viewer = Blackrock()


# ══════════════════════════════════════════════════════════════════════════════
#  Handler: /bi TICKER  (BlackRock Indonesia)
# ══════════════════════════════════════════════════════════════════════════════

async def blackrock_indonesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    await handle_blackrock_command(update, context, 'indonesia')


# ══════════════════════════════════════════════════════════════════════════════
#  Handler: /spdr TICKER
# ══════════════════════════════════════════════════════════════════════════════

async def spdr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    await handle_blackrock_command(update, context, 'spdr')


# ── Core handler (dipakai /bi dan /spdr) ──────────────────────────────────────

async def handle_blackrock_command(update: Update, context: ContextTypes.DEFAULT_TYPE, region: str):
    if not await check_public_group_access(update, active_admins):
        return

    viewer.load_blackrock_data_for_region(region)

    if viewer.blackrock_data[region] is None:
        company_name = viewer.company_names.get(region, region.upper())
        await update.message.reply_text(f"❌ Tidak ada data {company_name} yang ter-load.")
        return

    parts = update.message.text.split()
    if len(parts) < 2:
        company_name = viewer.company_names.get(region, region.upper())
        await update.message.reply_text(
            f"❌ Gunakan: /{parts[0].lstrip('/')} TICKER\nContoh: /{parts[0].lstrip('/')} BBCA"
        )
        return

    ticker = parts[1].upper()

    try:
        chart_buffer, caption = viewer.create_blackrock_chart(region, ticker)
        if chart_buffer is None:
            company_name = viewer.company_names.get(region, region.upper())
            await update.message.reply_text(
                f"❌ {company_name} tidak memegang saham {ticker}."
            )
            viewer.blackrock_data[region] = None
            return

        await update.message.reply_photo(photo=chart_buffer, caption=caption)
        viewer.blackrock_data[region] = None

    except Exception as e:
        company_name = viewer.company_names.get(region, region.upper())
        await update.message.reply_text(f"❌ Error membuat chart {company_name}: {str(e)}")
        viewer.blackrock_data[region] = None


# ══════════════════════════════════════════════════════════════════════════════
#  Handler: /b7  (Significant Movements — BlackRock + SPDR)
# ══════════════════════════════════════════════════════════════════════════════

async def blackrock_significant_movements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not (is_authorized_user(uid) or is_vip_user(uid)):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke bot ini.")
        return

    viewer.load_blackrock_data()

    try:
        for region in viewer.blackrock_folders.keys():
            viewer.load_blackrock_data_for_region(region)

        movements = viewer.get_significant_movements(0.3)

        if not movements:
            await update.message.reply_text(
                "📊 No significant Manajer Investasi movements found in the last period."
            )
            return

        # Label region singkat
        region_map = {'indonesia': 'BK', 'spdr': 'SP'}

        if len(movements) > 50:
            from datetime import datetime as dt

            csv_content = "No,Ticker,Region,Change%,Latest_Date,Previous_Date,Qty,MV\n"
            for i, m in enumerate(movements):
                csv_content += (
                    f"{i+1},{m['ticker']},{m['region'].upper()},"
                    f"{m['change_pct']:.2f},"
                    f"{m['latest_date'].strftime('%Y-%m-%d')},"
                    f"{m['previous_date'].strftime('%Y-%m-%d')},"
                    f"{m['latest_qty']:.0f},"
                    f"{m['latest_mv']:.0f}\n"
                )

            file_buffer      = io.BytesIO(csv_content.encode())
            file_buffer.name = f"movements_{dt.now().strftime('%Y%m%d_%H%M')}.csv"

            await update.message.reply_document(
                document=file_buffer,
                filename=file_buffer.name,
                caption=f"📊 {len(movements)} significant movements (>= 0.3%) — BlackRock & SPDR"
            )

            summary  = "📊 <b>Summary Report</b>\n\n<pre>"
            summary += f"Total movements : {len(movements)}\n"
            summary += f"Largest increase: {max(movements, key=lambda x: x['change_pct'])['change_pct']:+.2f}%\n"
            summary += f"Largest decrease: {min(movements, key=lambda x: x['change_pct'])['change_pct']:+.2f}%</pre>"
            await update.message.reply_text(summary, parse_mode='HTML')

        else:
            header        = "📊 <b>Pergerakan Signifikan — BlackRock & SPDR</b>\n\n"
            messages      = []
            current_msg   = header
            table_header  = (
                "<pre>"
                "No  Ticker   Src  Change%     Qty(K)   Date\n"
                "─────────────────────────────────────────────\n"
            )
            current_msg += table_header

            for i, m in enumerate(movements):
                arrow          = "↗" if m['change_pct'] > 0 else "↘"
                region_display = region_map.get(m['region'].lower(), m['region'].upper()[:2])

                row = (
                    f"{i+1:2d}  {m['ticker']:<8} {region_display:<3} "
                    f"{arrow}{m['change_pct']:+6.2f}% "
                    f"{m['latest_qty']/1000:>8.0f}K "
                    f"{m['latest_date'].strftime('%d%b')}\n"
                )

                if len(current_msg + row + "</pre>") > 4000:
                    current_msg += "</pre>"
                    messages.append(current_msg)
                    current_msg = header + table_header + row
                else:
                    current_msg += row

            current_msg += "</pre>"
            messages.append(current_msg)

            for msg in messages:
                await update.message.reply_text(msg, parse_mode='HTML')

    except Exception as e:
        await update.message.reply_text(f"❌ Error getting significant movements: {str(e)}")

    finally:
        # Reset semua region
        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None
