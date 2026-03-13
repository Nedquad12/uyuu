from impor import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Blackrock :
    def __init__(self, data_folder=None):
        print("✅ Utama siap digunakan")
        
        self.company_names = {
            'indonesia': 'BlackRock Indonesia',
            'btc': 'BlackRock Bitcoin',
            'dim': 'Dimensional',
            'spdr': 'SPDR',
            'jp': 'JP Morgan',
            'x': 'GlobalX',
            'gs': 'GoldmanSachs',
            'sch': 'SCHWAB',
            'ws': 'WisdomTree',
            'inv': 'Invesco',
            'fid': 'First Trust',
            'col': 'Columbia',
            'ksa': 'Blackrock Saudi Arabia'                
        }
        
        # BlackRock folders
        self.blackrock_folders = {
            'indonesia': "/home/ec2-user/database/br/ind",
            'btc': "/home/ec2-user/database/br/btc",
            'dim': "/home/ec2-user/database/br/dim",
            'spdr': "/home/ec2-user/database/br/spdr",
            'jp': "/home/ec2-user/database/br/jp",
            'x': "/home/ec2-user/database/br/globalx" ,
            'gs': "/home/ec2-user/database/br/goldman",
            'sch': "/home/ec2-user/database/br/schwab",
            'ws': "/home/ec2-user/database/br/ws",
            'inv': "/home/ec2-user/database/br/invesco",
            'fid': "/home/ec2-user/database/br/first",
            'col': "/home/ec2-user/database/br/columbia" ,
            'ksa': "/home/ec2-user/database/br/ksa"
            }
        
        # Data storage
        self.combined_df = None
        self.user_data = {}  # Store user-specific data (like chart selections)
        
        # BlackRock data storage
        self.blackrock_data = {
            'indonesia': None,
            'btc': None,
            'dim': None,
            'spdr': None,
            'jp' : None,
            'x' : None,
            'gs': None,
            'sch': None,
            'ws': None,
            'inv': None,
            'fid': None,
            'col': None,
            'ksa': None
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
               'indonesia': None,
               'btc': None,
               'dim': None,
               'spdr': None,
                'jp' : None,
                'x' : None,
                'gs': None,
                'sch': None,
                'ws': None,
                'inv': None,
                'fid': None,
                'col': None,
                'ksa': None
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
    
    def search_ticker_all_regions(self, ticker):
        """Search ticker across all loaded regions"""
        results = {}

        for region, data in self.blackrock_data.items():
            if data is None:
               continue
        
        # Make a copy and ensure Ticker column is string
            data_copy = data.copy()
            data_copy['Ticker'] = data_copy['Ticker'].astype(str).fillna('')
            data_copy = data_copy[~data_copy['Ticker'].isin(['', 'nan', 'None'])]
        
        # Format ticker based on region
            formatted_ticker = self.format_ticker_for_region(ticker, region)
    
        # Search in this region - now safe to use .str
            ticker_data = data_copy[data_copy['Ticker'].str.upper() == str(formatted_ticker).upper()]
    
            if not ticker_data.empty:
                results[region] = {
                    'data': ticker_data,
                    'formatted_ticker': formatted_ticker
            }

        return results

    def format_ticker_for_region(self, ticker, region):
        """Format ticker based on region requirements"""
    
    # Remove existing suffixes first
        clean_ticker = ticker.replace(' IJ', '').replace('.IJ', '')
    
        if region == 'btc':
        # Bitcoin uses BTC directly
            return 'BTC' if clean_ticker.upper() in ['BTC', 'BITCOIN'] else clean_ticker
        elif region in ['dim', 'x', 'ws', 'inv']:
        # These regions use ' IJ' suffix
            return f"{clean_ticker} IJ"
        elif region == 'fid':
        # First Trust uses '.IJ' suffix
            return f"{clean_ticker}.IJ"
        else:
        # Other regions (indonesia, spdr, jp, gs, sch) use ticker as-is
            return clean_ticker

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