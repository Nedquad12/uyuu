from impor import *

class TradingAnalyzer:
    def __init__(self):
        self.user_data = {}  # Dictionary untuk menyimpan data per user
        self.user_cache = {}  # Dictionary untuk cache per user
        self.data_folder = r"/home/ec2-user/order"
        
    def _get_user_key(self, user_id):
        """Generate cache key for user"""
        return f"user_{user_id}"
        
    def _is_cache_valid(self, user_id, stock_code):
        """Check if cache is still valid (5 minutes)"""
        user_key = self._get_user_key(user_id)
        if user_key not in self.user_cache:
            return False
            
        cache_data = self.user_cache[user_key]
        if cache_data['stock_code'] != stock_code:
            return False
            
        # Check if 5 minutes have passed
        cache_time = cache_data['timestamp']
        current_time = datetime.now()
        time_diff = current_time - cache_time
        
        return time_diff.total_seconds() < 200  # 5 minutes = 300 seconds
        
    def load_stock_data(self, stock_code, user_id):
        """Load stock data from Excel file for specific user"""
        user_key = self._get_user_key(user_id)
        
        # Check cache first
        if self._is_cache_valid(user_id, stock_code):
            # Use cached data
            cached_data = self.user_cache[user_key]
            self.user_data[user_key] = {
                'df': cached_data['df'],
                'processed_data': cached_data['processed_data'],
                'current_stock': cached_data['stock_code']
            }
            return True, f"Data {stock_code} dimuat dari cache"
        
        try:
            file_path = os.path.join(self.data_folder, f"{stock_code}.xlsx")
            if not os.path.exists(file_path):
                file_path = os.path.join(self.data_folder, f"{stock_code}.xls")
                if not os.path.exists(file_path):
                    return False, "Kode saham tidak ditemukan di database. Beritahu admin untuk menambahkan kode saham. Kontak admin @rendanggedang atau https://x.com/saberial_link/"
            
            df = pd.read_excel(file_path)
            
            # Initialize user data if not exists
            if user_key not in self.user_data:
                self.user_data[user_key] = {}
                
            self.user_data[user_key]['df'] = df
            self.user_data[user_key]['current_stock'] = stock_code.upper()
            self.process_data(user_id)
            
            # Cache the data
            self.user_cache[user_key] = {
                'stock_code': stock_code.upper(),
                'df': df,
                'processed_data': self.user_data[user_key]['processed_data'],
                'timestamp': datetime.now()
            }
            
            return True, f"Data {stock_code} berhasil dimuat dan di-cache"
            
        except Exception as e:
            return False, f"Error loading file: {str(e)}"
    
    def process_data(self, user_id):
        """Process and prepare data for analysis for specific user"""
        user_key = self._get_user_key(user_id)
    
        if user_key not in self.user_data or self.user_data[user_key]['df'] is None:
             return
    
        df = self.user_data[user_key]['df'].copy()
        
        # Convert Time to datetime
        df['Time'] = pd.to_datetime(df['Time'], format='%H:%M:%S').dt.time

       # Remove commas from Price and convert to float
        if 'Price' in df.columns:
           df['Price'] = df['Price'].astype(str).str.replace(',', '').astype(float)

       # ===== TAMBAHAN BARU: Aggregate transaksi dengan waktu dan broker yang sama =====
       # Group by Time, BT, BC, ST, SC - hanya gabung jika SEMUA kolom ini sama
        groupby_cols = ['Time', 'BT', 'BC', 'ST', 'SC']
        agg_dict = {
             'Qty': 'sum',      # Jumlahkan quantity
             'Price': 'mean'    # Rata-rata harga
            }

       # Aggregate data dengan waktu dan broker yang persis sama
        df_aggregated = df.groupby(groupby_cols, as_index=False, dropna=False).agg(agg_dict)

         # Gunakan data yang sudah di-aggregate
        df = df_aggregated.copy()

        
        # Create quantity categories
        def categorize_qty(qty):
            if qty <= 100:
                return 'micro'
            elif qty <= 500:
                return 'small'
            elif qty <= 3000:
                return 'medium'
            elif qty <= 15000:
                return 'big'
            else:
                return 'whale'
        
        df['Category'] = df['Qty'].apply(categorize_qty)
        
        # Create time intervals
        def get_time_bucket_10min(time_obj):
            dt = datetime.combine(datetime.today(), time_obj)
            minutes = dt.minute
            bucket_minute = (minutes // 10) * 10
            return dt.replace(minute=bucket_minute, second=0).time()

        def get_time_bucket_30min(time_obj):
            dt = datetime.combine(datetime.today(), time_obj)
            minutes = dt.minute
            bucket_minute = (minutes // 30) * 30
            return dt.replace(minute=bucket_minute, second=0).time()

        df['TimeBucket10Min'] = df['Time'].apply(get_time_bucket_10min)
        df['TimeBucket30Min'] = df['Time'].apply(get_time_bucket_30min)
        
        # Identify Buy/Sell transactions
        df['IsBuy'] = df['BT'].notna() & (df['BT'] != '') & df['BC'].notna() & (df['BC'] != '')
        df['IsSell'] = df['ST'].notna() & (df['ST'] != '') & df['SC'].notna() & (df['SC'] != '')

        # Extract broker codes
        df['BuyBrokerCode'] = df['BC'].fillna('').astype(str).str.strip()
        df['SellBrokerCode'] = df['SC'].fillna('').astype(str).str.strip()

        # Extract trader type
        df['BuyTraderType'] = df['BT'].fillna('').astype(str).str.strip()
        df['SellTraderType'] = df['ST'].fillna('').astype(str).str.strip()

        # Determine active broker code
        df['BrokerCode'] = df.apply(lambda x: 
           x['BuyBrokerCode'] if x['IsBuy'] 
           else x['SellBrokerCode'] if x['IsSell']
           else '', axis=1)

        df['TraderTypeClean'] = df.apply(lambda x:
           x['BuyTraderType'] if x['IsBuy']
           else x['SellTraderType'] if x['IsSell'] 
           else '', axis=1)
        
        # Create transaction direction
        df['Direction'] = df.apply(lambda x: 'Buy' if x['IsBuy'] else 'Sell' if x['IsSell'] else 'Unknown', axis=1)
        
        self.user_data[user_key]['processed_data'] = df

    def generate_broker_chart(self, interval='30min', category='All', user_id=None):
        """Generate broker analysis chart for specific user"""
        user_key = self._get_user_key(user_id)

        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return None, "No data loaded"

        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
        
        title = f'Top Broker Analysis - {current_stock} ({interval})'
        if category != 'All':
            title += f' ({category.title()} Category)'


    # Set time bucket based on interval
        time_bucket_col = 'TimeBucket30Min' if interval == '30min' else 'TimeBucket10Min'
        filtered_df = processed_data.copy()  # FIXED here
        filtered_df['TimeBucket'] = filtered_df[time_bucket_col]
        
        # Filter by category if specified
        if category != 'All':
            filtered_df = filtered_df[filtered_df['Category'] == category]
        
        if filtered_df.empty:
            return None, "No data to display"
        
        # Analyze buy and sell by broker code
        buy_data = filtered_df[filtered_df['IsBuy'] == True]
        sell_data = filtered_df[filtered_df['IsSell'] == True]
        
        buy_by_broker = buy_data.groupby('BuyBrokerCode')['Qty'].sum().sort_values(ascending=False)
        sell_by_broker = sell_data.groupby('SellBrokerCode')['Qty'].sum().sort_values(ascending=False)
        
        # Get top brokers
        all_brokers = set(buy_by_broker.index) | set(sell_by_broker.index)
        broker_totals = {}
        
        for broker in all_brokers:
            if broker and broker.strip() and broker != 'nan':
                buy_qty = buy_by_broker.get(broker, 0)
                sell_qty = sell_by_broker.get(broker, 0)
                broker_totals[broker] = buy_qty + sell_qty
        
        # Sort brokers by total activity and take top 15
        top_brokers = sorted(broker_totals.items(), key=lambda x: x[1], reverse=True)[:15]
        top_broker_codes = [broker[0] for broker in top_brokers]
        
        # Prepare data for plotting
        buy_quantities = [buy_by_broker.get(broker, 0) for broker in top_broker_codes]
        sell_quantities = [sell_by_broker.get(broker, 0) for broker in top_broker_codes]
        
        # Create matplotlib figure
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(14, 8))
        
        x = np.arange(len(top_broker_codes))
        width = 0.35
        
        # Create clustered bar chart
        bars1 = ax.bar(x - width/2, buy_quantities, width, label='Buy Volume', 
                       color='#2E8B57', alpha=0.8)
        bars2 = ax.bar(x + width/2, sell_quantities, width, label='Sell Volume', 
                       color='#DC143C', alpha=0.8)
        
        # Customize chart
        ax.set_xlabel('Broker Code', fontsize=12)
        ax.set_ylabel('Quantity', fontsize=12)
    
        if category != 'All':
            title += f' ({category.title()} Category)'
        
        ax.set_title(title, fontsize=14)
        ax.set_xticks(x)
        ax.set_xticklabels(top_broker_codes, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        # Add value labels on bars
        def add_value_labels(bars, values):
            for bar, value in zip(bars, values):
                if value > 0:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + max(buy_quantities + sell_quantities)*0.01,
                           f'{value:,}', ha='center', va='bottom', fontsize=8, rotation=0)
        
        add_value_labels(bars1, buy_quantities)
        add_value_labels(bars2, sell_quantities)
        
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        
        return img_buffer, "Chart generated successfully"

    def generate_pie_chart(self, category='All', user_id=None):
        """Generate pie chart for broker distribution"""
        user_key = self._get_user_key(user_id)
    
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return None, "No data loaded"
    
        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
    
        filtered_df = processed_data.copy()
    
        # Create matplotlib figure
        fig, ax = plt.subplots(figsize=(10, 8))
        
        category = category
        if category == 'All':
            # Show distribution by category
            category_data = processed_data.groupby('Category')['Qty'].sum()
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57']
            
            wedges, texts, autotexts = ax.pie(category_data.values, labels=category_data.index, 
                                              autopct='%1.1f%%', startangle=90, colors=colors)
            
            ax.set_title(f'Distribution by Category - {current_stock}')
            
            # Add legend with quantities
            legend_labels = [f'{cat}: {qty:,}' for cat, qty in category_data.items()]
            ax.legend(wedges, legend_labels, title="Categories", loc="center left", 
                     bbox_to_anchor=(1, 0, 0.5, 1))
        else:
            # Show broker distribution for selected category
            filtered_df = filtered_df[filtered_df['Category'] == category]
            
            # Group by broker code
            broker_data = filtered_df.groupby('BrokerCode')['Qty'].sum().sort_values(ascending=False)
            
            # Take top 10 brokers
            if len(broker_data) > 10:
                top_brokers = broker_data.head(10)
                others_sum = broker_data.tail(len(broker_data) - 10).sum()
                if others_sum > 0:
                    top_brokers['Others'] = others_sum
                broker_data = top_brokers
            
            # Create pie chart for brokers
            colors = plt.cm.Set3(range(len(broker_data)))
            wedges, texts, autotexts = ax.pie(broker_data.values, labels=broker_data.index, 
                                              autopct='%1.1f%%', startangle=90, colors=colors)
            
            ax.set_title(f'Broker Distribution - {current_stock} ({category.title()} Category)')
            
            # Add legend with quantities
            legend_labels = [f'{broker}: {qty:,}' for broker, qty in broker_data.items()]
            ax.legend(wedges, legend_labels, title="Brokers", loc="center left", 
                     bbox_to_anchor=(1, 0, 0.5, 1))
        
        # Enhance text readability
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_weight('bold')
        
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=200, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        
        return img_buffer, "Pie chart generated successfully"

    def get_broker_details(self, broker_code, interval='30min', user_id=None):
        """Get detailed analysis for specific broker"""
        user_key = self._get_user_key(user_id)
       
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return "No data loaded"
    
        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
    
    # Set time bucket based on interval
        time_bucket_col = 'TimeBucket30Min' if interval == '30min' else 'TimeBucket10Min'
        data = processed_data.copy()
        
        # Set time bucket based on interval
        time_bucket_col = 'TimeBucket30Min' if interval == '30min' else 'TimeBucket10Min'
        data = processed_data.copy()
        data['TimeBucket'] = data[time_bucket_col]
        
        # Filter data for this broker
        broker_buy_data = data[(data['IsBuy'] == True) & (data['BuyBrokerCode'] == broker_code)]
        broker_sell_data = data[(data['IsSell'] == True) & (data['SellBrokerCode'] == broker_code)]
        
        # Format detailed analysis
        detail_text = (
             "============================\n"
             "📢 Owner: https://x.com/saberial_link/\n"
             "============================\n\n"
            f"📊 BROKER ANALYSIS: {broker_code}\n"
        )
        detail_text += f"📈 Stock: {current_stock}\n"
        detail_text += f"⏱️ Interval: {interval}\n"
        detail_text += "=" * 40 + "\n\n"
        
        # Buy Analysis
        detail_text += "🟢 BUY TRANSACTIONS:\n"
        detail_text += "-" * 30 + "\n"
        if not broker_buy_data.empty:
            buy_total = broker_buy_data['Qty'].sum()
            buy_count = len(broker_buy_data)
            buy_avg = buy_total / buy_count if buy_count > 0 else 0
            buy_avg_price = broker_buy_data['Price'].mean()
            buy_total_value = (broker_buy_data['Price'] * broker_buy_data['Qty']).sum() * 100
            
            detail_text += f"Total Buy Quantity: {buy_total:,}\n"
            detail_text += f"Number of Transactions: {buy_count:,}\n"
            detail_text += f"Average Buy Size: {buy_avg:,.0f}\n"
            detail_text += f"Average Buy Price: {buy_avg_price:,.0f}\n"
            detail_text += f"Total Buy Value: Rp {buy_total_value:,.0f}\n"
            
            # Buy by time bucket
            buy_by_time = broker_buy_data.groupby('TimeBucket').agg({
                'Qty': 'sum',
                'Price': 'mean'
            }).sort_index()
            
            buy_value_by_time = broker_buy_data.groupby('TimeBucket', group_keys=False).apply(
                lambda x: (x['Price'] * x['Qty']).sum() * 100
            ).sort_index()
            
            detail_text += "\n📊 Buy by Time:\n"
            for time_bucket, row in buy_by_time.iterrows():
                qty = row['Qty']
                avg_price = row['Price']
                value = buy_value_by_time.get(time_bucket, 0)
                detail_text += f"{str(time_bucket)}: {qty:,} @ {avg_price:,.0f} (Rp {value:,.0f})\n"
        else:
            detail_text += "No buy transactions found.\n"
        
        detail_text += "\n"
        
        # Sell Analysis
        detail_text += "🔴 SELL TRANSACTIONS:\n"
        detail_text += "-" * 30 + "\n"
        if not broker_sell_data.empty:
            sell_total = broker_sell_data['Qty'].sum()
            sell_count = len(broker_sell_data)
            sell_avg = sell_total / sell_count if sell_count > 0 else 0
            sell_avg_price = broker_sell_data['Price'].mean()
            sell_total_value = (broker_sell_data['Price'] * broker_sell_data['Qty']).sum() * 100
            
            detail_text += f"Total Sell Quantity: {sell_total:,}\n"
            detail_text += f"Number of Transactions: {sell_count:,}\n"
            detail_text += f"Average Sell Size: {sell_avg:,.0f}\n"
            detail_text += f"Average Sell Price: {sell_avg_price:,.0f}\n"
            detail_text += f"Total Sell Value: Rp {sell_total_value:,.0f}\n"
            
            # Sell by time bucket
            sell_by_time = broker_sell_data.groupby('TimeBucket').agg({
                'Qty': 'sum',
                'Price': 'mean'
            }).sort_index()
            
            sell_value_by_time = broker_sell_data.groupby('TimeBucket', group_keys=False).apply(
                lambda x: (x['Price'] * x['Qty']).sum() * 100
            ).sort_index()
            
            detail_text += "\n📊 Sell by Time:\n"
            for time_bucket, row in sell_by_time.iterrows():
                qty = row['Qty']
                avg_price = row['Price']
                value = sell_value_by_time.get(time_bucket, 0)
                detail_text += f"{str(time_bucket)}: {qty:,} @ {avg_price:,.0f} (Rp {value:,.0f})\n"
        else:
            detail_text += "No sell transactions found.\n"
        
        # Net Analysis
        buy_total = broker_buy_data['Qty'].sum() if not broker_buy_data.empty else 0
        sell_total = broker_sell_data['Qty'].sum() if not broker_sell_data.empty else 0
        net_position = buy_total - sell_total
        
        detail_text += "\n" + "=" * 40 + "\n"
        detail_text += "📊 NET POSITION SUMMARY:\n"
        detail_text += "-" * 30 + "\n"
        detail_text += f"Total Buy:  {buy_total:,}\n"
        detail_text += f"Total Sell: {sell_total:,}\n"
        detail_text += f"Net Position: {net_position:,} "
        
        if net_position > 0:
            detail_text += "(🟢 NET BUYER)\n"
        elif net_position < 0:
            detail_text += "(🔴 NET SELLER)\n"
        else:
            detail_text += "(⚪ BALANCED)\n"
        
        return detail_text

    def get_broker_list(self, user_id=None):
        """Get list of available brokers"""
        user_key = self._get_user_key(user_id)
    
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
           return []
    
        processed_data = self.user_data[user_key]['processed_data']
    
    # Get all unique broker codes
        buy_brokers = processed_data['BuyBrokerCode'].unique()
        sell_brokers = processed_data['SellBrokerCode'].unique()
    
        all_brokers = set()
        for broker in buy_brokers:
            if broker and broker.strip() and broker != 'nan':
               all_brokers.add(broker.strip())
        for broker in sell_brokers:
            if broker and broker.strip() and broker != 'nan':
               all_brokers.add(broker.strip())
    
        return sorted(list(all_brokers))
    
    def load_combined_stock_data(self, stock_code, user_id, max_days=10):
       """Load and combine stock data from multiple days"""
       user_key = self._get_user_key(user_id)
    
       combined_df = pd.DataFrame()
       loaded_files = []
    
       try:
           # Load main file (today's data)
           main_file = os.path.join(self.data_folder, f"{stock_code}.xlsx")
           if not os.path.exists(main_file):
               main_file = os.path.join(self.data_folder, f"{stock_code}.xls")
               if not os.path.exists(main_file):
                   return False, f"File utama {stock_code} tidak ditemukan"
        
           main_df = pd.read_excel(main_file)
           main_df['Day'] = 0  # Today
           combined_df = pd.concat([combined_df, main_df], ignore_index=True)
           loaded_files.append(f"{stock_code} (hari ini)")
        
           # Load historical files (1-10 days ago)
           for day in range(1, max_days + 1):
                file_path_xlsx = os.path.join(self.data_folder, f"{stock_code}{day}.xlsx")
                file_path_xls = os.path.join(self.data_folder, f"{stock_code}{day}.xls")
            
                if os.path.exists(file_path_xlsx):
                    day_df = pd.read_excel(file_path_xlsx)
                    day_df['Day'] = day
                    combined_df = pd.concat([combined_df, day_df], ignore_index=True)
                    loaded_files.append(f"{stock_code}{day} ({day} hari lalu)")
                elif os.path.exists(file_path_xls):
                   day_df = pd.read_excel(file_path_xls)
                   day_df['Day'] = day
                   combined_df = pd.concat([combined_df, day_df], ignore_index=True)
                   loaded_files.append(f"{stock_code}{day} ({day} hari lalu)")
        
           if combined_df.empty:
               return False, "Tidak ada data yang berhasil dimuat"
        
           # Initialize user data if not exists
           if user_key not in self.user_data:
               self.user_data[user_key] = {}
            
           self.user_data[user_key]['df'] = combined_df
           self.user_data[user_key]['current_stock'] = f"{stock_code}_COMBINED"
           self.user_data[user_key]['loaded_files'] = loaded_files
           self.process_data(user_id)
        
          # Cache the combined data
           self.user_cache[user_key] = {
               'stock_code': f"{stock_code}_COMBINED",
               'df': combined_df,
               'processed_data': self.user_data[user_key]['processed_data'],
               'timestamp': datetime.now()
          }
        
           files_info = "\n".join(loaded_files)
           return True, f"Data gabungan {stock_code} berhasil dimuat:\n{files_info}\n\nTotal {len(loaded_files)} file dimuat"
        
       except Exception as e:
                return False, f"Error loading combined data: {str(e)}"
            
    