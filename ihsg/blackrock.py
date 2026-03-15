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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Blackrock :
    def __init__(self, data_folder=None):
        print("✅ Utama siap digunakan")
        
        self.company_names = {
            'indonesia': 'BlackRock Indonesia'             
        }
        
        # BlackRock folders
        self.blackrock_folders = {
            'indonesia': "/home/ec2-user/database/br/ind"
            }
        
        # Data storage
        self.combined_df = None
        self.user_data = {}  # Store user-specific data (like chart selections)
        
        # BlackRock data storage
        self.blackrock_data = {
            'indonesia': None
        }
        
        self.watchlist_data = None
        self.watchlist_averages = None
    def load_blackrock_data(self):
        """Load BlackRock data from all folders"""
        for region, folder_path in self.blackrock_folders.items():
            try:
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)
                    logger.info(f"📂 Created BlackRock folder: {folder_path}")
                    continue

                # Find Excel files
                excel_files = []
                for extension in ['*.xlsx', '*.xls']:
                    excel_files.extend(glob.glob(os.path.join(folder_path, extension)))

                if not excel_files:
                    logger.warning(f"⚠️ No BlackRock files found in {region}")
                    continue

                # Sort files by date (newest first) and limit to 60
                excel_files = sorted(excel_files, reverse=True)[:60]
                logger.info(f"📄 Found {len(excel_files)} BlackRock files for {region}")

                dataframes = []
                for file_path in excel_files:
                    try:
                        # Extract date from filename (ddmmyy.xlsx)
                        filename = os.path.basename(file_path)
                        date_str = filename.split('.')[0]
                        
                        df = pd.read_excel(file_path)
                        
                        # Add date column based on filename
                        if len(date_str) == 6:  # ddmmyy format
                            day = int(date_str[:2])
                            month = int(date_str[2:4])
                            year = int('20' + date_str[4:6])  # assume 20xx
                            file_date = datetime(year, month, day)
                            df['Date'] = file_date
                        
                        dataframes.append(df)
                        logger.info(f"✅ Loaded BlackRock file: {filename} for {region}")
                        
                    except Exception as e:
                        logger.error(f"❌ Error loading BlackRock file {file_path}: {e}")
                        continue

                if dataframes:
                    self.blackrock_data[region] = pd.concat(dataframes, ignore_index=True)
                    self.blackrock_data[region] = self.blackrock_data[region].sort_values('Date', ascending=True)
                    logger.info(f"✅ Loaded {len(self.blackrock_data[region])} BlackRock records for {region}")

            except Exception as e:
                logger.error(f"❌ Error loading BlackRock data for {region}: {e}")
                
    def load_blackrock_data_for_region(self, region):
        """Load BlackRock data for a specific region only"""
        folder_path = self.blackrock_folders.get(region)
        if not folder_path or not os.path.exists(folder_path):
            logger.warning(f"⚠️ Folder not found for BlackRock region: {region}")
            if self.blackrock_data is None:
               self.blackrock_data = {
               'indonesia': None
             }

        excel_files = []
        for extension in ['*.xlsx', '*.xls']:
            excel_files.extend(glob.glob(os.path.join(folder_path, extension)))

        if not excel_files:
            logger.warning(f"⚠️ No BlackRock files found in {region}")
            self.blackrock_data[region] = None
            return

        excel_files = sorted(excel_files, reverse=True)[:60]
        logger.info(f"📄 Found {len(excel_files)} BlackRock files for {region}")

        dataframes = []
        for file_path in excel_files:
            try:
                df = pd.read_excel(file_path)
                filename = os.path.basename(file_path)
                date_str = filename.split('.')[0]
                if len(date_str) == 6:  # ddmmyy format
                    day = int(date_str[:2])
                    month = int(date_str[2:4])
                    year = int('20' + date_str[4:6])  # assume 20xx
                    file_date = datetime(year, month, day)
                    df['Date'] = file_date
                dataframes.append(df)
            except Exception as e:
                logger.error(f"❌ Error loading BlackRock file {file_path}: {e}")
                continue

        if dataframes:
            self.blackrock_data[region] = pd.concat(dataframes, ignore_index=True)
            self.blackrock_data[region] = self.blackrock_data[region].sort_values('Date', ascending=True)
            logger.info(f"✅ Loaded {len(self.blackrock_data[region])} BlackRock records for {region}")
        else:
            self.blackrock_data[region] = None
            
    def search_blackrock_ticker(self, region, ticker):
        """Search BlackRock data for specific ticker"""
        if region not in self.blackrock_data or self.blackrock_data[region] is None:
            return None
     
        data = self.blackrock_data[region].copy()
    
    # Ensure Ticker column is string and handle NaN values
        data['Ticker'] = data['Ticker'].astype(str).fillna('')
    
    # Remove any rows where Ticker is empty or 'nan'
        data = data[~data['Ticker'].isin(['', 'nan', 'None'])]
    
    # Now safely use .str accessor
        ticker_data = data[data['Ticker'].str.upper() == str(ticker).upper()]
    
        return ticker_data if not ticker_data.empty else None
    
    def create_combined_summary(self, ticker, search_results):
        """Create a summary of ticker across all regions"""
    
        if not search_results:
            return f"❌ Ticker {ticker} tidak ditemukan di semua Manager Investasi"
    
        summary = f"📊 Summary for {ticker}:\n\n"
    
        total_qty = 0
        total_mv = 0
        latest_date = None
    
        for region, result in search_results.items():
            company_name = self.company_names.get(region, 'BlackRock')
            data = result['data']
            formatted_ticker = result['formatted_ticker']
        
        # Get latest data for this region
            grouped = data.groupby('Date').last().sort_index()
            if len(grouped) > 0:
                latest = grouped.iloc[-1]
            
                summary += f"🏢 {company_name} ({region.upper()}):\n"
                summary += f"   Ticker: {formatted_ticker}\n"
                summary += f"   Quantity: {latest['Quantity Total']:,.0f}\n"
                summary += f"   Market Value: ${latest['Market Value Total']:,.0f}\n"
                summary += f"   Latest Date: {latest.name.strftime('%d-%b-%Y')}\n\n"
            
                total_qty += latest['Quantity Total']
                total_mv += latest['Market Value Total']
            
            if latest_date is None or latest.name > latest_date:
                latest_date = latest.name
    
        summary += f"📊 TOTAL Manager Investment:\n"
        summary += f"   Total Quantity: {total_qty:,.0f}\n"
        summary += f"   Total Market Value: ${total_mv:,.0f}\n"
        summary += f"   Latest Update: {latest_date.strftime('%d-%b-%Y') if latest_date else 'N/A'}\n"
    
        return summary
    
    def create_blackrock_chart(self, region, ticker):
        """Create chart for BlackRock ticker data"""
        ticker_data = self.search_blackrock_ticker(region, ticker)
        if ticker_data is None:
            return None, None
        
        # Group by date and get latest values for each date
        grouped = ticker_data.groupby('Date').last().sort_index()
        
        # Create chart for Quantity Total
        plt.figure(figsize=(12, 8))
        plt.plot(grouped.index, grouped['Quantity Total'], marker='o', linewidth=2, color='blue')
        company_name = self.company_names.get(region, 'BlackRock')
        plt.title(f'{company_name} Holdings - {ticker} ({region.upper()})', fontsize=14, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Quantity Total', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        plt.text(0.5, 0.5, 'Membahas Saham Indonesia', fontsize=60, color='gray',
         ha='center', va='center', alpha=0.2, rotation=30,
         transform=plt.gcf().transFigure, zorder=10)
        
        # Save chart to buffer
        chart_buf = io.BytesIO()
        plt.savefig(chart_buf, format='png', dpi=300, bbox_inches='tight')
        chart_buf.seek(0)
        plt.close('all')
        gc.collect()
        
        # Generate movement caption
        caption = self.generate_movement_caption(grouped, ticker, region)
        
        return chart_buf, caption
    
    def get_significant_movements(self, threshold=3.0):
        """Get all tickers with significant movements (>= threshold%)"""
        movements = []
    
        for region, data in self.blackrock_data.items():
            if data is None or len(data) < 2:
                continue
                
          # Make copy and ensure Ticker column is string
            data_copy = data.copy()
            data_copy['Ticker'] = data_copy['Ticker'].astype(str).fillna('')
            data_copy = data_copy[~data_copy['Ticker'].isin(['', 'nan', 'None'])]
        
        # Limit to latest 5 dates for /b7 command only
            latest_dates = sorted(data_copy['Date'].unique(), reverse=True)[:5]
            data_copy = data_copy[data_copy['Date'].isin(latest_dates)]
        
        # Get unique tickers
            tickers = data_copy['Ticker'].unique()
        
            for ticker in tickers:
                ticker_data = data_copy[data_copy['Ticker'] == ticker].groupby('Date').last().sort_index()
            
                if len(ticker_data) < 2:
                    continue
                
            # Calculate movement
                latest = ticker_data.iloc[-1]
                previous = ticker_data.iloc[-2]
            
                if previous['Quantity Total'] == 0:
                    continue
                
                qty_change_pct = ((latest['Quantity Total'] - previous['Quantity Total']) / previous['Quantity Total']) * 100
            
                if abs(qty_change_pct) >= threshold:
                    movements.append({
                        'region': region,
                         'ticker': ticker,
                         'change_pct': qty_change_pct,
                         'latest_qty': latest['Quantity Total'],
                         'previous_qty': previous['Quantity Total'],
                         'latest_mv': latest['Market Value Total'],
                         'previous_mv': previous['Market Value Total'],
                         'latest_date': latest.name,
                         'previous_date': previous.name
                    })
    
        # Sort by absolute change percentage
        movements.sort(key=lambda x: abs(x['change_pct']), reverse=True)
        return movements
    
    def generate_movement_caption(self, grouped_data, ticker, region):
        """Generate detailed movement caption"""
        if len(grouped_data) < 2:
            company_name = self.company_names.get(region, 'BlackRock')
            return f"📊 {company_name} Holdings - {ticker} ({region.upper()})\n❌ Insufficient data for movement analysis"
        
        # Get latest and previous data
        latest = grouped_data.iloc[-1]
        previous = grouped_data.iloc[-2]
        
        # Calculate changes
        qty_change = latest['Quantity Total'] - previous['Quantity Total']
        qty_change_pct = (qty_change / previous['Quantity Total']) * 100 if previous['Quantity Total'] != 0 else 0
        
        mv_change = latest['Market Value Total'] - previous['Market Value Total']
        mv_change_pct = (mv_change / previous['Market Value Total']) * 100 if previous['Market Value Total'] != 0 else 0
        
        # Format numbers
        qty_latest = f"{latest['Quantity Total']:,.0f}"
        qty_prev = f"{previous['Quantity Total']:,.0f}"
        mv_latest = f"{latest['Market Value Total']:,.0f}"
        mv_prev = f"{previous['Market Value Total']:,.0f}"
        
        # Direction indicators
        qty_arrow = "🔺" if qty_change > 0 else "🔻" if qty_change < 0 else "➡️"
        mv_arrow = "🔺" if mv_change > 0 else "🔻" if mv_change < 0 else "➡️"
        
        company_name = self.company_names.get(region, 'BlackRock')
        caption = f"""📊 {company_name} Holdings - {ticker} ({region.upper()})

📅 Latest: {latest.name.strftime('%d-%b-%Y')}
📅 Previous: {previous.name.strftime('%d-%b-%Y')}

📈 Quantity Total:
Current: {qty_latest}
Previous: {qty_prev}
Change: {qty_arrow} {qty_change:+,.0f} ({qty_change_pct:+.2f}%)

💰 Market Value Total:
Current: ${mv_latest}
Previous: ${mv_prev}
Change: {mv_arrow} ${mv_change:+,.0f} ({mv_change_pct:+.2f}%)"""
        
        return caption

viewer = Blackrock()

async def blackrock_significant_movements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    viewer.load_blackrock_data()
    
    """Show significant BlackRock movements (>= 0.3%) with compact monospace format"""
    try:
        for region in viewer.blackrock_folders.keys():
            viewer.load_blackrock_data_for_region(region)
        movements = viewer.get_significant_movements(0.3)
        
        if not movements:
            await update.message.reply_text("📊 No significant Manajer Investasi movements found in the last period.")
            return
        
        # Check if we need to send as file for large datasets
        if len(movements) > 50:
            import io
            from datetime import datetime
            
            # Create CSV content
            csv_content = "No,Ticker,Region,Change%,Latest_Date,Previous_Date,Qty,MV\n"
            for i, movement in enumerate(movements):
                csv_content += (
                    f"{i+1},{movement['ticker']},{movement['region'].upper()},"
                    f"{movement['change_pct']:.2f},"
                    f"{movement['latest_date'].strftime('%Y-%m-%d')},"
                    f"{movement['previous_date'].strftime('%Y-%m-%d')},"
                    f"{movement['latest_qty']:.0f},"
                    f"{movement['latest_mv']:.0f}\n"
                )
            
            # Send as file
            file_buffer = io.BytesIO(csv_content.encode())
            file_buffer.name = f"blackrock_movements_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            
            await update.message.reply_document(
                document=file_buffer,
                filename=file_buffer.name,
                caption=f"📊 {len(movements)} significant BlackRock movements (>= 0.3%)"
            )
            
            # Also send summary
            summary = f"📊 <b>Summary Report</b>\n\n"
            summary += f"<pre>Total movements: {len(movements)}\n"
            summary += f"Largest increase: {max(movements, key=lambda x: x['change_pct'])['change_pct']:+.2f}%\n"
            summary += f"Largest decrease: {min(movements, key=lambda x: x['change_pct'])['change_pct']:+.2f}%</pre>"
            
            await update.message.reply_text(summary, parse_mode='HTML')
            
        else:
            # Compact table format for smaller datasets
            header = "📊 <b>Pergerakan Signifikan Manajer Investasi</b>\n\n"
            messages = []
            current_message = header
            
            # Table header with monospace
            table_header = (
                "<pre>"
                "No  Ticker   Reg  Change%     Qty(K)     MV(M)   Date\n"
                "──────────────────────────────────────────────────────\n"
            )
            current_message += table_header
            
            # Region mapping for better display names
            region_map = {
                'indonesia': 'BK'
            }
            
            for i, movement in enumerate(movements):
                arrow = "↗" if movement['change_pct'] > 0 else "↘"
                region_display = region_map.get(movement['region'].lower(), movement['region'].upper()[:3])
                
                # Format compact row
                row = (
                    f"{i+1:2d}  {movement['ticker']:<8} {region_display:<3} "
                    f"{arrow}{movement['change_pct']:+6.2f}% "
                    f"{movement['latest_qty']/1000:>8.0f}K "
                    f"{movement['latest_mv']/1000000:>7.1f}M "
                    f"{movement['latest_date'].strftime('%d%b')}\n"
                )
                
                # Check if adding this row would exceed Telegram's limit
                if len(current_message + row + "</pre>") > 4000:
                    current_message += "</pre>"
                    messages.append(current_message)
                    current_message = header + table_header + row
                else:
                    current_message += row
            
            # Close the last message
            current_message += "</pre>"
            messages.append(current_message)
            
            # Send all messages
            for msg in messages:
                await update.message.reply_text(msg, parse_mode='HTML')
        
        # Clear BlackRock data from memory after use
        viewer.blackrock_data = {
            'indonesia': None
        }

        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting significant movements: {str(e)}")
        
        # Also clear data on error
        viewer.blackrock_data = {
            'indonesia': None
        }

        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting significant movements: {str(e)}")
        
        # Also clear data on error
        viewer.blackrock_data = {
            'indonesia': None
        }

        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None

async def blackrock_indonesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await handle_blackrock_command(update, context, 'indonesia')
        
async def handle_blackrock_command(update: Update, context: ContextTypes.DEFAULT_TYPE, region):
    """Handle BlackRock commands that require ticker input"""
    
    viewer.load_blackrock_data_for_region(region)
       
    if viewer.blackrock_data[region] is None:
        await update.message.reply_text(f"❌ No BlackRock {region} data loaded.")
        return
    
    parts = update.message.text.split()
    if len(parts) < 2:
        company_name = viewer.company_names.get(region, 'BlackRock')
        await update.message.reply_text(f"❌ No {company_name} {region} data in Blackrock Holding.")
        return
    
    ticker = parts[1].upper()        
    
    try:
        chart_buffer, caption = viewer.create_blackrock_chart(region, ticker)
        if chart_buffer is None:
            company_name = viewer.company_names.get(region, 'BlackRock')
            await update.message.reply_text(f"❌ {company_name} tidak memegang saham {ticker} in {region}")
            return
        
        await update.message.reply_photo(
        photo=chart_buffer,
        caption=caption
        )
        
        viewer.blackrock_data[region] = None
         
    except Exception as e:
        company_name = viewer.company_names.get(region, 'BlackRock')
        await update.message.reply_text(f"❌ Error membuat {company_name} {region} chart: {str(e)}")