from impor import*

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramStockDataViewer:
    def __init__(self, data_folder=None):
        print("✅ Utama siap digunakan")
         # Automatically set folder path
        if data_folder:
            self.data_folder = data_folder
        else:
            self.data_folder = "/home/ec2-user/database/data"  # Default relative folder
            
        self.margin_folder = "/home/ec2-user/database/margin"
        self.margin_df = None
        self.margin_fields = ['Volume', 'Nilai', 'Frekuensi']
        self.watchlist_folder = "/home/ec2-user/database/wl"
        self.chart_folder = "/home/ec2-user/database/foreign"
        self.user_data = {}

        # Available fields for plotting
        self.plot_fields = [
            'Local IS', 'Local CP', 'Local PF', 'Local IB', 'Local ID', 'Local MF', 'Local SC',
            'Foreign IS', 'Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign ID', 'Foreign MF', 'Foreign SC'
        ]
        
        # Nama cantik untuk tombol Telegram
        self.button_labels = {
            'Local IS': '🇮🇩 Lokal Asuransi',
            'Local CP': '🇮🇩 Lokal Korporat',
            'Local PF': '🇮🇩 Lokal Dana Pensiun',
            'Local IB': '🇮🇩 Lokal Bank',
            'Local ID': '🇮🇩 Lokal Ritel',
            'Local MF': '🇮🇩 Lokal Reksadana',
            'Local SC': '🇮🇩 Lokal Sekuritas',
            'Foreign IS': '🌏 Asing Asuransi',
            'Foreign CP': '🌏 Asing Korporat',
            'Foreign PF': '🌏 Asing Dana Pensiun',
            'Foreign IB': '🌏 Asing Bank',
            'Foreign ID': '🌏 Asing Ritel',
            'Foreign MF': '🌏 Asing Reksadana',
            'Foreign SC': '🌏 Asing Sekuritas'
             }
    
    def load_all_excel_files(self):
        """Load all Excel files from the data folder"""
        try:
            # Create data folder if it doesn't exist
            if not os.path.exists(self.data_folder):
                os.makedirs(self.data_folder)
                logger.info(f"📂 Created data folder: {self.data_folder}")
                return

            # Find all Excel files in the data folder
            excel_files = []
            for extension in ['*.xlsx', '*.xls', '*.XLSX', '*.XLS']:
                excel_files.extend(glob.glob(os.path.join(self.data_folder, extension)))

            if not excel_files:
                logger.warning("⚠️ No Excel files found in data folder")
                return

            logger.info(f"📄 Found {len(excel_files)} Excel files: {[os.path.basename(f) for f in excel_files]}")

            # Load all Excel files
            dataframes = []
            loaded_files = []

            for file_path in excel_files:
                try:
                    logger.info(f"📥 Loading file: {file_path}")
                    df = pd.read_excel(file_path)  # FIX: Use correct file path
                    dataframes.append(df)
                    loaded_files.append(os.path.basename(file_path))
                    logger.info(f"✅ Loaded: {os.path.basename(file_path)} - {len(df)} records")
                except Exception as e:
                    logger.error(f"❌ Error loading {file_path}: {e}")
                    continue

            if dataframes:
                # Combine all dataframes
                self.combined_df = self.combine_dataframes(dataframes)
                logger.info(f"✅ Successfully loaded {len(loaded_files)} files with {len(self.combined_df)} total records")
                logger.info(f"📅 Date range: {self.combined_df['Date'].min()} to {self.combined_df['Date'].max()}")
            else:
                logger.error("❌ No valid Excel files could be loaded")
                
            self.margin_df = None  

        except Exception as e:
            logger.error(f"❌ Error during auto-load: {e}")
            
    def load_margin_files(self):
        """Load margin trading files from margin folder"""
        try:
            if not os.path.exists(self.margin_folder):
                os.makedirs(self.margin_folder)
                logger.info(f"📂 Created margin folder: {self.margin_folder}")
                return

        # Find Excel files with ddmmyy.xlsx pattern
            excel_files = []
            for extension in ['*.xlsx', '*.xls']:
                excel_files.extend(glob.glob(os.path.join(self.margin_folder, extension)))

            if not excel_files:
               logger.warning("⚠️ No margin Excel files found")
               return

        # Limit to 60 files and sort by date
            excel_files = sorted(excel_files)[:60]
            logger.info(f"📄 Found {len(excel_files)} margin files")

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
                    logger.info(f"✅ Loaded margin file: {filename}")
                
                except Exception as e:
                    logger.error(f"❌ Error loading margin file {file_path}: {e}")
                    continue

            if dataframes:
                self.margin_df = pd.concat(dataframes, ignore_index=True)
                self.margin_df = self.margin_df.sort_values('Date', ascending=True)
                logger.info(f"✅ Loaded {len(self.margin_df)} margin records")

        except Exception as e:
            logger.error(f"❌ Error loading margin files: {e}")
    
    def load_watchlist_data(self):
        """Load watchlist data from data folder for analysis"""
        try:
            if not os.path.exists(self.watchlist_folder):
                logger.warning("⚠️ Data folder not found for watchlist")
                return

           # Find Excel files with ddmmyy.xlsx pattern
            excel_files = []
            for extension in ['*.xlsx', '*.xls']:
                excel_files.extend(glob.glob(os.path.join(self.watchlist_folder, extension)))

            if not excel_files:
                logger.warning("⚠️ No Excel files found for watchlist")
                return

        # Sort files by date (newest first) and limit to 60
            excel_files = sorted(excel_files, reverse=True)[:60]
            logger.info(f"📄 Found {len(excel_files)} files for watchlist")

            dataframes = []
            for file_path in excel_files:
                try:
                # Extract date from filename (ddmmyy.xlsx)
                    filename = os.path.basename(file_path)
                    date_str = filename.split('.')[0]
                
                    df = pd.read_excel(file_path)
                
                # Check if required columns exist
                    required_cols = ['Kode Saham', 'Penutupan', 'Volume', 'Frekuensi', 
                                   'Foreign Buy', 'Foreign Sell', 'Listed Shares']
                    missing_cols = [col for col in required_cols if col not in df.columns]
                
                    if missing_cols:
                       logger.warning(f"Missing columns in {filename}: {missing_cols}")
                       continue
                
                # Add date column based on filename
                    if len(date_str) == 6:  # ddmmyy format
                        day = int(date_str[:2])
                        month = int(date_str[2:4])
                        year = int('20' + date_str[4:6])  # assume 20xx
                        file_date = datetime(year, month, day)
                        df['Date'] = file_date
                
                # Select only required columns
                    df = df[required_cols + ['Date']]
                    dataframes.append(df)
                    logger.info(f"✅ Loaded watchlist file: {filename}")
                
                except Exception as e:
                    logger.error(f"❌ Error loading watchlist file {file_path}: {e}")
                    continue

            if dataframes:
                self.watchlist_data = pd.concat(dataframes, ignore_index=True)
                self.watchlist_data = self.watchlist_data.sort_values('Date', ascending=False)
            
            # Calculate averages
                self.calculate_watchlist_averages()
                logger.info(f"✅ Loaded {len(self.watchlist_data)} watchlist records")

        except Exception as e:
           logger.error(f"❌ Error loading watchlist data: {e}")
    
    def get_user_data(self, user_id):
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'chart_selections': set()
            }
        return self.user_data[user_id]
    
    def load_excel_file(self, file_path):
        try:
            df = pd.read_excel(file_path)
            return df
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}")
            return None
    
    def combine_dataframes(self, dfs):
        try:
        # Combine all dataframes
           combined_df = pd.concat(dfs, ignore_index=True)
        
        # Convert Date column
           combined_df['Date'] = pd.to_datetime(combined_df['Date'])
        
        # Remove duplicates based on Date and Code
           combined_df = combined_df.drop_duplicates(subset=['Date', 'Code'], keep='last')
        
        # Sort by date (oldest first - ascending order)
           combined_df = combined_df.sort_values('Date', ascending=True)
        
           return combined_df
        except Exception as e:
           logger.error(f"Error combining dataframes: {e}")
        return None
    
    def search_margin_stock(self, code):
        """Search margin data for specific stock"""
        if self.margin_df is None:
            return None
    
        stock_data = self.margin_df[self.margin_df['Kode Saham'].str.upper() == code.upper()]
        return stock_data if not stock_data.empty else None
    
    def search_stock(self, code, limit=6):
        if self.combined_df is None:
           return None
    
    # Filter data by code and limit to specified records (oldest first)
        stock_data = self.combined_df[self.combined_df['Code'].str.upper() == code.upper()].head(limit)
    
        if stock_data.empty:
           return None
    
    # Debug: Print raw data to check for duplicates
        logger.info(f"Raw data for {code}:\n{stock_data[['Date', 'Code']]}")
    
        return stock_data
    
    def calculate_watchlist_averages(self):
        """Calculate average Volume and Frekuensi from all data"""
        if self.watchlist_data is None:
            return
     
        try:
        # Calculate averages across all data
            self.watchlist_averages = {
                'avg_volume': self.watchlist_data['Volume'].mean(),
                'avg_frekuensi': self.watchlist_data['Frekuensi'].mean()
        }
        
            logger.info(f"📊 Calculated averages - Volume: {self.watchlist_averages['avg_volume']:,.0f}, Frekuensi: {self.watchlist_averages['avg_frekuensi']:,.0f}")
        
        except Exception as e:
            logger.error(f"❌ Error calculating averages: {e}")

    def get_watchlist_stocks(self, cap_filter=None):
        """Get stocks that meet watchlist criteria"""
        if self.watchlist_data is None or self.watchlist_averages is None:
            return []
    
        try:
        # Get latest data for each stock
            latest_data = self.watchlist_data.groupby('Kode Saham').first().reset_index()
        
        # Calculate thresholds (70% above average)
            volume_threshold = self.watchlist_averages['avg_volume'] * 1.7
            frekuensi_threshold = self.watchlist_averages['avg_frekuensi'] * 1.7
        
        # Filter stocks meeting criteria
            filtered_stocks = latest_data[
                (latest_data['Volume'] >= volume_threshold) & 
                (latest_data['Frekuensi'] >= frekuensi_threshold)
            ].copy()
        
        # Calculate additional metrics
            filtered_stocks['Net Foreign'] = filtered_stocks['Foreign Buy'] - filtered_stocks['Foreign Sell']
            filtered_stocks['Market Cap'] = filtered_stocks['Penutupan'] * filtered_stocks['Listed Shares']
        
        # Apply market cap filter
            if cap_filter:
                if cap_filter == 'high':
                    filtered_stocks = filtered_stocks[filtered_stocks['Market Cap'] >= 20e12]  # ≥20T
                elif cap_filter == 'mid':
                    filtered_stocks = filtered_stocks[
                       (filtered_stocks['Market Cap'] >= 1e12) & 
                       (filtered_stocks['Market Cap'] < 20e12)
                    ]  # ≥1T and <20T
                elif cap_filter == 'low':
                    filtered_stocks = filtered_stocks[
                        (filtered_stocks['Market Cap'] >= 80e9) & 
                        (filtered_stocks['Market Cap'] < 1e12)
                    ]  # ≥80M and <1T
                elif cap_filter == 'micro':
                    filtered_stocks = filtered_stocks[filtered_stocks['Market Cap'] < 80e9]  # <80M
                     
            foreign_60d = (
                self.watchlist_data.groupby('Kode Saham')
                .apply(lambda x: (x.sort_values('Date', ascending=False).head(60)['Foreign Buy'].sum() -
                            x.sort_values('Date', ascending=False).head(60)['Foreign Sell'].sum()))
               .reset_index(name='Net Foreign 60D')
          ) 

        # Gabungkan hasil ke filtered_stocks
            filtered_stocks = filtered_stocks.merge(foreign_60d, on='Kode Saham', how='left')
        
            return filtered_stocks.to_dict('records')
        
        except Exception as e:
            logger.error(f"❌ Error getting watchlist stocks: {e}")
            return []

    def get_foreign_flow_data(self, stock_code, days=30):
        """Get foreign flow data for specific stock"""
        if self.watchlist_data is None:
            return None
    
        try:
            stock_data = self.watchlist_data[
                self.watchlist_data['Kode Saham'].str.upper() == stock_code.upper()
            ].head(days)
        
            if stock_data.empty:
                return None
        
            stock_data = stock_data.copy()
            stock_data['Net Foreign'] = stock_data['Foreign Buy'] - stock_data['Foreign Sell']
        
            return stock_data[['Date', 'Foreign Buy', 'Foreign Sell', 'Net Foreign']].to_dict('records')
        
        except Exception as e:
            logger.error(f"❌ Error getting foreign flow data: {e}")
            return None
    
    def get_all_stock_codes(self):
        """Get all unique stock codes from the data"""
        if self.combined_df is None:
           return []

        if 'Code' not in self.combined_df.columns:
           logger.error("❌ Column 'Code' not found in data")
           return []

        try:
          # Pastikan hanya ambil nilai string
           codes = self.combined_df['Code'].dropna()
           codes = codes[codes.apply(lambda x: isinstance(x, str))]
           return sorted(codes.unique())
        except Exception as e:
           logger.error(f"❌ Error getting stock codes: {e}")
           return []
   
    def get_data_info(self):
        """Get information about the loaded data"""
        # Regular data info
        if self.combined_df is None:
            regular_info = "No regular data loaded"
        else:
            total_records = len(self.combined_df)
            unique_codes = len(self.combined_df['Code'].unique())
            date_range = f"{self.combined_df['Date'].min().strftime('%d-%b-%Y')} to {self.combined_df['Date'].max().strftime('%d-%b-%Y')}"
            regular_info = {
                'total_records': total_records,
                'unique_codes': unique_codes,
                'date_range': date_range
            }

        # Margin data info
        if self.margin_df is None:
            margin_info = "No margin data loaded"
        else:
            margin_records = len(self.margin_df)
            margin_codes = len(self.margin_df['Kode Saham'].unique())
            margin_range = f"{self.margin_df['Date'].min().strftime('%d-%b-%Y')} to {self.margin_df['Date'].max().    strftime('%d-%b-%Y')}"
            margin_info = {
                'total_records': margin_records,
                'unique_codes': margin_codes,
                'date_range': margin_range
            }

        return {
            'regular': regular_info,
            'margin': margin_info
        }   
    
    def format_stock_data(self, data):
        if data is None or data.empty:
            return "No data found"
        
        local_columns = ['Local IS', 'Local CP', 'Local PF', 'Local IB', 'Local ID', 'Local MF', 'Local SC']
        foreign_columns = ['Foreign IS', 'Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign ID', 'Foreign MF', 'Foreign SC']
        
        result = []
        for _, row in data.iterrows():
            # Calculate totals
            local_total = sum(row.get(col, 0) for col in local_columns if pd.notna(row.get(col, 0)))
            foreign_total = sum(row.get(col, 0) for col in foreign_columns if pd.notna(row.get(col, 0)))
            
            result.append(f"📅 {row['Date'].strftime('%d-%b-%Y')}")
            result.append(f"🏷️ Code: {row.get('Code', '')}")
            result.append(f"📊 Type: {row.get('Type', '')}")
            result.append(f"💰 Price: {row.get('Price', 0):,.0f}")
            result.append(f"🏠 Total Local: {local_total:,.0f}")
            result.append(f"🌍 Total Foreign: {foreign_total:,.0f}")
            result.append("─" * 30)
        
        return "\n".join(result)
    
    def create_margin_charts(self, code):
        """Create 3 separate bar charts for Volume, Nilai, Frekuensi"""
        margin_data = self.search_margin_stock(code)
        if margin_data is None:
            return None

        grouped = margin_data.groupby('Date')[self.margin_fields].sum().sort_index()

        fig, axes = plt.subplots(3, 1, figsize=(12, 15))

        # Volume Chart (Bar)
        axes[0].bar(grouped.index, grouped['Volume'], color='blue')
        axes[0].set_title(f'Volume - {code}', fontsize=14, fontweight='bold')
        axes[0].set_ylabel('Volume')
        axes[0].grid(True, alpha=0.3)

    # Nilai Chart (Bar)
        axes[1].bar(grouped.index, grouped['Nilai'], color='green')
        axes[1].set_title(f'Nilai - {code}', fontsize=14, fontweight='bold')
        axes[1].set_ylabel('Nilai')
        axes[1].grid(True, alpha=0.3)

    # Frekuensi Chart (Bar)
        axes[2].bar(grouped.index, grouped['Frekuensi'], color='red')
        axes[2].set_title(f'Frekuensi - {code}', fontsize=14, fontweight='bold')
        axes[2].set_ylabel('Frekuensi')
        axes[2].set_xlabel('Date')
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d%m'))
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()

      # Watermark
        plt.text(0.5, 0.5, 'Membahas Saham Indonesia', fontsize=60, color='gray',
                 ha='center', va='center', alpha=0.2, rotation=30,
                 transform=plt.gcf().transFigure, zorder=10)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close('all')
        gc.collect()

        return buf
    
    def create_excel_report(self, data, file_path, code):
        """Create Excel report with Shares and Value sheets"""
        wb = Workbook()
        
        # Get latest price (from most recent date)
        latest_price = data.sort_values('Date', ascending=False).iloc[0]['Price']
        
        # Define styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                       top=Side(style='thin'), bottom=Side(style='thin'))
        center_align = Alignment(horizontal='center')
        number_format = '#,##0'  # Format: 1.111.111
        currency_format = '_("Rp"* #,##0_);_("Rp"* (#,##0);_("Rp"* "-"_);_(@_)'
        percentage_format = '0.00"%"'
        
        # ===== SHEET 1: SHARES =====
        ws_shares = wb.active
        ws_shares.title = "Shares"
        
        # Headers for Shares (kolom A-X)
        headers_shares = ['Date', 'Code', 'Type', 'Price',
                         'Local IS', 'Local CP', 'Local PF', 'Local IB', 'Local ID', 'Local MF', 'Local SC', 'Local FD', 'Local OT',
                         'Total Local',
                         'Foreign IS', 'Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign ID', 'Foreign MF', 'Foreign SC', 'Foreign FD', 'Foreign OT',
                         'Total Foreign']
        
        # Write headers
        for col, header in enumerate(headers_shares, 1):
            cell = ws_shares.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = center_align
        
        # Write data for Shares
        local_categories = ['Local IS', 'Local CP', 'Local PF', 'Local IB', 'Local ID', 'Local MF', 'Local SC', 'Local FD', 'Local OT']
        foreign_categories = ['Foreign IS', 'Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign ID', 'Foreign MF', 'Foreign SC', 'Foreign FD', 'Foreign OT']
        
        for row_idx, (_, row_data) in enumerate(data.iterrows(), 2):
            # Kolom A-D: Date, Code, Type, Price
            ws_shares.cell(row=row_idx, column=1, value=row_data['Date'].strftime('%d-%b-%Y')).border = border
            ws_shares.cell(row=row_idx, column=2, value=row_data.get('Code', '')).border = border
            ws_shares.cell(row=row_idx, column=3, value=row_data.get('Type', '')).border = border
            ws_shares.cell(row=row_idx, column=4, value=row_data.get('Price', 0)).border = border
            
            # Kolom E-M: Local IS to Local OT (format: 1.111.111)
            for col_idx, cat in enumerate(local_categories, 5):
                value = row_data.get(cat, 0)
                cell = ws_shares.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border
                cell.number_format = number_format
            
            # Kolom N: Total Local (formula)
            local_range = f"E{row_idx}:M{row_idx}"
            total_local_cell = ws_shares.cell(row=row_idx, column=14)
            total_local_cell.value = f"=SUM({local_range})"
            total_local_cell.border = border
            total_local_cell.number_format = number_format
            
            # Kolom O-W: Foreign IS to Foreign OT (format: 1.111.111)
            for col_idx, cat in enumerate(foreign_categories, 15):
                value = row_data.get(cat, 0)
                cell = ws_shares.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border
                cell.number_format = number_format
            
            # Kolom X: Total Foreign (formula)
            foreign_range = f"O{row_idx}:W{row_idx}"
            total_foreign_cell = ws_shares.cell(row=row_idx, column=24)
            total_foreign_cell.value = f"=SUM({foreign_range})"
            total_foreign_cell.border = border
            total_foreign_cell.number_format = number_format
        
        # Auto-adjust column widths for Shares
        for column in ws_shares.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 20)
            ws_shares.column_dimensions[column_letter].width = adjusted_width
        
        # ===== SHEET 2: VALUE =====
        ws_value = wb.create_sheet(title="Value")
        
        # Headers for Value (kolom A-X, kolom D kosong)
        headers_value = ['Date', 'Code', 'Type', '',
                        'Local IS', 'Local CP', 'Local PF', 'Local IB', 'Local ID', 'Local MF', 'Local SC', 'Local FD', 'Local OT',
                        'Total Local',
                        'Foreign IS', 'Foreign CP', 'Foreign PF', 'Foreign IB', 'Foreign ID', 'Foreign MF', 'Foreign SC', 'Foreign FD', 'Foreign OT',
                        'Total Foreign']
        
        # Write headers for Value
        for col, header in enumerate(headers_value, 1):
            if header:  # Skip empty header
                cell = ws_value.cell(row=1, column=col, value=header)
                cell.font = header_font
                cell.fill = header_fill
                cell.border = border
                cell.alignment = center_align
        
        # Write data for Value (shares × latest_price)
        for row_idx, (_, row_data) in enumerate(data.iterrows(), 2):
            # Kolom A-C: Date, Code, Type
            ws_value.cell(row=row_idx, column=1, value=row_data['Date'].strftime('%d-%b-%Y')).border = border
            ws_value.cell(row=row_idx, column=2, value=row_data.get('Code', '')).border = border
            ws_value.cell(row=row_idx, column=3, value=row_data.get('Type', '')).border = border
            # Kolom D: KOSONG (tidak ada Price)
            ws_value.cell(row=row_idx, column=4, value='').border = border
            
            # Kolom E-M: Local IS to Local OT (shares × price, format Rupiah)
            for col_idx, cat in enumerate(local_categories, 5):
                shares = row_data.get(cat, 0)
                value_idr = shares * latest_price
                cell = ws_value.cell(row=row_idx, column=col_idx, value=value_idr)
                cell.border = border
                cell.number_format = currency_format
            
            # Kolom N: Total Local (formula)
            total_local_cell = ws_value.cell(row=row_idx, column=14)
            total_local_cell.value = f"=SUM(E{row_idx}:M{row_idx})"
            total_local_cell.border = border
            total_local_cell.number_format = currency_format
            
            # Kolom O-W: Foreign IS to Foreign OT (shares × price, format Rupiah)
            for col_idx, cat in enumerate(foreign_categories, 15):
                shares = row_data.get(cat, 0)
                value_idr = shares * latest_price
                cell = ws_value.cell(row=row_idx, column=col_idx, value=value_idr)
                cell.border = border
                cell.number_format = currency_format
            
            # Kolom X: Total Foreign (formula)
            total_foreign_cell = ws_value.cell(row=row_idx, column=24)
            total_foreign_cell.value = f"=SUM(O{row_idx}:W{row_idx})"
            total_foreign_cell.border = border
            total_foreign_cell.number_format = currency_format
        
        # ===== OWNERSHIP PERCENTAGE (below Value data) =====
        last_data_row = len(data) + 1
        pct_start_row = last_data_row + 3
        
        # Header section
        ws_value.cell(row=pct_start_row, column=1, value="OWNERSHIP PERCENTAGE (%)").font = Font(bold=True, size=12)
        
        # Column headers for percentage
        ws_value.cell(row=pct_start_row+1, column=1, value="Date").fill = header_fill
        ws_value.cell(row=pct_start_row+1, column=1).font = header_font
        ws_value.cell(row=pct_start_row+1, column=1).border = border
        
        pct_headers = ['Local IS%', 'Local CP%', 'Local PF%', 'Local IB%', 'Local ID%', 'Local MF%', 'Local SC%', 'Local FD%', 'Local OT%',
                       'Foreign IS%', 'Foreign CP%', 'Foreign PF%', 'Foreign IB%', 'Foreign ID%', 'Foreign MF%', 'Foreign SC%', 'Foreign FD%', 'Foreign OT%']
        
        for col_idx, header in enumerate(pct_headers, 2):
            cell = ws_value.cell(row=pct_start_row+1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
        
        # Write percentage data
        for data_row_idx, (_, row_data) in enumerate(data.iterrows(), 2):
            pct_row = pct_start_row + 1 + (data_row_idx - 1)
            
            # Date
            ws_value.cell(row=pct_row, column=1, value=row_data['Date'].strftime('%d-%b-%Y')).border = border
            
            # Local percentages (each local category / Total Local × 100)
            for i in range(9):
                col_letter = get_column_letter(5 + i)  # E to M (Local categories)
                total_local_col = 'N'  # Total Local column
                formula = f"=IF({total_local_col}{data_row_idx}=0,0,{col_letter}{data_row_idx}/{total_local_col}{data_row_idx}*100)"
                cell = ws_value.cell(row=pct_row, column=2+i, value=formula)
                cell.border = border
                cell.number_format = percentage_format
            
            # Foreign percentages (each foreign category / Total Foreign × 100)
            for i in range(9):
                col_letter = get_column_letter(15 + i)  # O to W (Foreign categories)
                total_foreign_col = 'X'  # Total Foreign column
                formula = f"=IF({total_foreign_col}{data_row_idx}=0,0,{col_letter}{data_row_idx}/{total_foreign_col}{data_row_idx}*100)"
                cell = ws_value.cell(row=pct_row, column=11+i, value=formula)
                cell.border = border
                cell.number_format = percentage_format
        
        # Auto-adjust column widths for Value
        for column in ws_value.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 20)
            ws_value.column_dimensions[column_letter].width = adjusted_width
        
        wb.save(file_path)
    
    
    def create_line_chart(self, selected_fields, code=None):
        if self.combined_df is None:
            return None
        
        # Make a copy of the dataframe
        df = self.combined_df.copy()
        
        # Calculate totals if needed
        if 'Total Local' in selected_fields:
            df['Total Local'] = df[[f for f in self.plot_fields if f.startswith('Local')]].sum(axis=1)
        if 'Total Foreign' in selected_fields:
            df['Total Foreign'] = df[[f for f in self.plot_fields if f.startswith('Foreign')]].sum(axis=1)
        
        # Filter stock if applicable
        if code:
            df = df[df['Code'].str.upper() == code.upper()]
            if df.empty:
                return None
            
            
        
        # Group by date and sum
        grouped = df.groupby('Date')[selected_fields].sum().sort_index()
        
        plt.figure(figsize=(12, 8))
        for field in selected_fields:
            plt.plot(grouped.index, grouped[field], marker='o', label=field, linewidth=2)
        
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Value', fontsize=12)
        plt.title(f"Line Chart{' for ' + code if code else ''}", fontsize=14, fontweight='bold')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        plt.text(0.5, 0.5, 'Membahas Saham Indonesia', fontsize=60, color='gray',
            ha='center', va='center', alpha=0.2, rotation=30,
            transform=plt.gcf().transFigure, zorder=10)
        
        # Save to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        buf.seek(0)
        plt.close('all')
        gc.collect()
        
        return buf

    def get_foreign_flow_data(self, stock_code, days=30):
        """Get foreign flow data for specific stock"""
        if self.watchlist_data is None:
            return None
    
        try:
            stock_data = self.watchlist_data[
                self.watchlist_data['Kode Saham'].str.upper() == stock_code.upper()
            ].head(days)
        
            if stock_data.empty:
                return None
        
            stock_data = stock_data.copy()
            stock_data['Net Foreign'] = stock_data['Foreign Buy'] - stock_data['Foreign Sell']
        
            return stock_data[['Date', 'Foreign Buy', 'Foreign Sell', 'Net Foreign']].to_dict('records')
        
        except Exception as e:
           logger.error(f"❌ Error getting foreign flow data: {e}")
           return None

    def format_watchlist_response(self, stocks, cap_filter=None):
        """Format watchlist response for Telegram"""
        if not stocks:
            return "❌ No stocks found meeting the criteria"
    
        cap_names = {
            'high': 'High Cap (≥20T)',
            'mid': 'Mid Cap (≥1T)',
            'low': 'Low Cap (≥80M)',
            'micro': 'Micro Cap (<80M)'
       }
    
        header = f"📊 WATCHLIST STOCKS"
        if cap_filter:
            header += f" - {cap_names.get(cap_filter, cap_filter.upper())}"
    
            summary = f"""
📈 Avg Volume    : {self.watchlist_averages['avg_volume']:,.0f}
🔄 Avg Frekuensi : {self.watchlist_averages['avg_frekuensi']:,.0f}
📊 Threshold     : Vol≥{self.watchlist_averages['avg_volume']*1.7:,.0f}, Freq≥{self.watchlist_averages['avg_frekuensi']*1.7:,.0f}
"""
    
        # Header tabel
        rows = []
        rows.append(f"{'No':<3} {'Kode':<6} {'Price':>7} {'Cap':>6} {'Vol':>8} {'Freq':>7} {'NetF':>9} {'F60d':>10}")
        rows.append("-" * 65)
        # Sort by market cap descending
        stocks_sorted = sorted(stocks, key=lambda x: x['Market Cap'], reverse=True)
     
        for i, stock in enumerate(stocks_sorted, 1): 
        # Format market cap
            market_cap = stock['Market Cap']
            if market_cap >= 1e12:
                cap_str = f"{market_cap/1e12:.1f}T"
            elif market_cap >= 1e9:
                cap_str = f"{market_cap/1e9:.1f}B"
            else:
                cap_str = f"{market_cap/1e6:.1f}M"
        
            # Format foreign
            price = stock['Penutupan']
            vol = stock['Volume']
            freq = stock['Frekuensi']
            nf_today = stock.get('Net Foreign', 0)
            nf_60d = stock.get('Net Foreign 60D', 0)

            rows.append(f"{i:<3} {stock['Kode Saham']:<6} {price:>7,.0f} {cap_str:>6} {vol:>8,} {freq:>7,} {nf_today:>+9,} {nf_60d:>+10,}")

        return f"```{header}\n{summary.strip()}\n\n" + "\n".join(rows) + "```"
 
    def get_foreign_summary_by_days(self, stock_code, days_list=[10, 15, 30, 45, 60]):
        if self.watchlist_data is None:
            return None

        try:
            stock_data = self.watchlist_data[
                self.watchlist_data['Kode Saham'].str.upper() == stock_code.upper()
            ].sort_values('Date', ascending=False)

            if stock_data.empty:
                return None

            summary = []
            for days in days_list:
                subset = stock_data.head(days)
                buy_total = subset['Foreign Buy'].sum()
                sell_total = subset['Foreign Sell'].sum()
                net = buy_total - sell_total
                summary.append((days, buy_total, sell_total, net))

            return summary
        except Exception as e:
            logger.error(f"❌ Error getting foreign summary by days: {e}")
            return None
