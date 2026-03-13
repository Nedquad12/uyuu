from impor import *

class PriceFlowAnalyzer:
    def __init__(self):
        self.user_data = {}  # Dictionary untuk menyimpan data per user
        self.user_cache = {}  # Dictionary untuk cache per user
        self.data_folder = r"/home/ec2-user/data"
        
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
        
        return time_diff.total_seconds() < 300  # 5 minutes = 300 seconds
        
    def load_flow_data(self, stock_code, user_id, max_days=10):
        """Load and combine flow data from multiple days"""
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
    
        combined_df = pd.DataFrame()
        loaded_files = []
    
        try:
        # Load main file (today's data)
            main_file = os.path.join(self.data_folder, f"{stock_code}.xlsx")
            if not os.path.exists(main_file):
                main_file = os.path.join(self.data_folder, f"{stock_code}.xls")
                if not os.path.exists(main_file):
                   return False, f"File utama {stock_code} tidak ditemukan di folder data"
           
            main_df = pd.read_excel(main_file)
        
        # Kolom wajib: Price, Qty
            needed_cols = {'Price', 'Qty'}
            missing = needed_cols - set(main_df.columns)
            if missing:
                return False, f"File utama kurang kolom: {', '.join(missing)}"
            
            main_df['Day'] = 0  # Today
            combined_df = pd.concat([combined_df, main_df], ignore_index=True)
            loaded_files.append(f"{stock_code} (hari ini)")
        
         # Load historical files (1-10 days ago) - PERBAIKAN DI SINI
            for day in range(1, max_days + 1):
               # Format yang benar: STOCKCODE + DAY + .xlsx/xls
                file_path_xlsx = os.path.join(self.data_folder, f"{stock_code}{day}.xlsx")
                file_path_xls = os.path.join(self.data_folder, f"{stock_code}{day}.xls")
            
                day_df = None
                file_used = None
            
            # Coba xlsx dulu, lalu xls
                if os.path.exists(file_path_xlsx):
                    try:
                        day_df = pd.read_excel(file_path_xlsx)
                        file_used = f"{stock_code}{day}.xlsx"
                    except Exception as e:
                        print(f"Error reading {file_path_xlsx}: {str(e)}")
                        continue
                    
                elif os.path.exists(file_path_xls):
                    try:
                        day_df = pd.read_excel(file_path_xls)
                        file_used = f"{stock_code}{day}.xls"
                    except Exception as e:
                        print(f"Error reading {file_path_xls}: {str(e)}")
                        continue
            
                if day_df is not None and not day_df.empty:
                # Check if required columns exist
                    if needed_cols.issubset(set(day_df.columns)):
                        day_df['Day'] = day
                        combined_df = pd.concat([combined_df, day_df], ignore_index=True)
                        loaded_files.append(f"{file_used} ({day} hari lalu)")
                    else:
                        print(f"File {file_used} missing required columns: {needed_cols - set(day_df.columns)}")
                        continue
        
            if combined_df.empty:
                return False, "Tidak ada data yang berhasil dimuat"
        
        # Initialize user data if not exists
            if user_key not in self.user_data:
                self.user_data[user_key] = {}
            
            self.user_data[user_key]['df'] = combined_df
            self.user_data[user_key]['current_stock'] = f"{stock_code}_FLOW"
            self.user_data[user_key]['loaded_files'] = loaded_files
            self.process_flow_data(user_id)
        
        # Cache the combined data
            self.user_cache[user_key] = {
                'stock_code': f"{stock_code}_FLOW",
                'df': combined_df,
                'processed_data': self.user_data[user_key]['processed_data'],
                'timestamp': datetime.now()
            }
        
            files_info = "\n".join(loaded_files)
            return True, f"Data flow {stock_code} berhasil dimuat:\n{files_info}\n\nTotal {len(loaded_files)} file dimuat"
        
        except Exception as e:
            return False, f"Error loading flow data: {str(e)}"

    
    def process_flow_data(self, user_id):
        """Process and prepare data for flow analysis"""
        user_key = self._get_user_key(user_id)
        
        if user_key not in self.user_data or 'df' not in self.user_data[user_key]:
            return
        
        df = self.user_data[user_key]['df'].copy()
        
        # Clean and convert Price column
        if 'Price' in df.columns:
            # Remove commas and convert to float
            df['Price'] = df['Price'].astype(str).str.replace(',', '').astype(float)
        
        # Clean and convert Qty column
        if 'Qty' in df.columns:
            # Remove commas and convert to int
            df['Qty'] = df['Qty'].astype(str).str.replace(',', '').astype(int)
        
        # Remove invalid data
        df = df.dropna(subset=['Price', 'Qty'])
        df = df[(df['Price'] > 0) & (df['Qty'] > 0)]
        
        # ===== KUNCI: Group by Price dan sum Qty =====
        # Ini adalah inti dari permintaan - menggabungkan quantity untuk price yang sama
        price_flow = df.groupby('Price', as_index=False)['Qty'].sum()
        
        # Sort by Qty descending (quantity terbanyak di atas)
        price_flow = price_flow.sort_values('Qty', ascending=False).reset_index(drop=True)
        
        # Add additional analysis columns
        price_flow['Percentage'] = (price_flow['Qty'] / price_flow['Qty'].sum()) * 100
        price_flow['Cumulative_Qty'] = price_flow['Qty'].cumsum()
        price_flow['Cumulative_Pct'] = (price_flow['Cumulative_Qty'] / price_flow['Qty'].sum()) * 100
        
        # Calculate total value for each price level
        price_flow['Total_Value'] = price_flow['Price'] * price_flow['Qty'] * 100  # Multiply by 100 for IDR
        
        # Add rank
        price_flow['Rank'] = price_flow.index + 1
        
        self.user_data[user_key]['processed_data'] = price_flow
        
    def get_flow_analysis(self, user_id, limit=None):
        """Get price flow analysis in text format"""
        user_key = self._get_user_key(user_id)
      
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
            return "No data loaded"
    
        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
    
    # Limit results if specified
        if limit:
            display_data = processed_data.head(limit)
            title_suffix = f" (Top {limit})"
        else:
            display_data = processed_data
            title_suffix = " (Full Analysis)"
    
    # Create analysis text with monospace formatting
        analysis_text = (
        "```\n"  # Start monospace block
        "============================\n"
        "📊 Owner: https://x.com/saberial_link/\n"
        "============================\n\n"
        f"💹 PRICE FLOW ANALYSIS: {current_stock}{title_suffix}\n"
        f"📈 Total Price Levels: {len(processed_data):,}\n"
        f"📊 Total Quantity: {processed_data['Qty'].sum():,}\n"
        f"💰 Total Value: Rp {processed_data['Total_Value'].sum():,.0f}\n"
        "=" * 50 + "\n\n"
    )
    
        analysis_text += "🔍 PRICE FLOW BREAKDOWN:\n"
        analysis_text += "-" * 50 + "\n"
        analysis_text += f"{'Rank':<4} {'Price':<10} {'Qty':<12} {'%':<6} {'Value (Rp)':<15}\n"
        analysis_text += "-" * 50 + "\n"
    
        for _, row in display_data.iterrows():
            rank = int(row['Rank'])
            price = row['Price']
            qty = int(row['Qty'])
            pct = row['Percentage']
            value = row['Total_Value']
        
            analysis_text += f"{rank:<4} {price:<10,.0f} {qty:<12,} {pct:<6.1f} {value:<15,.0f}\n"
    
    # Add summary statistics
        analysis_text += "\n" + "=" * 50 + "\n"
        analysis_text += "📊 SUMMARY STATISTICS:\n"
        analysis_text += "-" * 30 + "\n"
    
    # Top 10% analysis
        top_10_pct = processed_data.head(int(len(processed_data) * 0.1))
        top_10_qty = top_10_pct['Qty'].sum()
        top_10_pct_of_total = (top_10_qty / processed_data['Qty'].sum()) * 100
    
        analysis_text += f"🎯 Top 10% Price Levels: {len(top_10_pct):,} levels\n"
        analysis_text += f"📈 Contains: {top_10_qty:,} qty ({top_10_pct_of_total:.1f}% of total)\n"
    
    # Price range
        min_price = processed_data['Price'].min()
        max_price = processed_data['Price'].max()
        avg_price = processed_data['Price'].mean()
    
        analysis_text += f"💰 Price Range: {min_price:,.0f} - {max_price:,.0f}\n"
        analysis_text += f"📊 Average Price: {avg_price:,.0f}\n"
    
    # Most active price level
        most_active = processed_data.iloc[0]
        analysis_text += f"🔥 Most Active Price: {most_active['Price']:,.0f} ({most_active['Qty']:,} qty)\n"
    
        analysis_text += "```"  # End monospace block
    
        return analysis_text

    
    def generate_flow_chart(self, user_id):
        """Generate price flow chart"""
        user_key = self._get_user_key(user_id)
        
        if user_key not in self.user_data or self.user_data[user_key].get('processed_data') is None:
            return None, "No data loaded"
        
        processed_data = self.user_data[user_key]['processed_data']
        current_stock = self.user_data[user_key]['current_stock']
        
        # Take top 20 for better visualization
        top_data = processed_data.head(20)
        
        # Create matplotlib figure
        plt.style.use('default')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12))
        
        # Chart 1: Bar chart of top price levels
        bars = ax1.bar(range(len(top_data)), top_data['Qty'], 
                       color='#2E8B57', alpha=0.8)
        
        ax1.set_xlabel('Price Level Rank', fontsize=12)
        ax1.set_ylabel('Quantity', fontsize=12)
        ax1.set_title(f'Top 20 Price Levels - {current_stock}', fontsize=14)
        ax1.grid(True, alpha=0.3, axis='y')
        
        # Add price labels on x-axis
        price_labels = [f"{price:,.0f}" for price in top_data['Price']]
        ax1.set_xticks(range(len(top_data)))
        ax1.set_xticklabels(price_labels, rotation=45, ha='right')
        
        # Add value labels on bars
        for bar, qty in zip(bars, top_data['Qty']):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + max(top_data['Qty'])*0.01,
                    f'{qty:,}', ha='center', va='bottom', fontsize=8, rotation=0)
        
        # Chart 2: Cumulative percentage
        ax2.plot(range(len(top_data)), top_data['Cumulative_Pct'], 
                 marker='o', linewidth=2, color='#DC143C')
        ax2.fill_between(range(len(top_data)), top_data['Cumulative_Pct'], 
                         alpha=0.3, color='#DC143C')
        
        ax2.set_xlabel('Price Level Rank', fontsize=12)
        ax2.set_ylabel('Cumulative Percentage (%)', fontsize=12)
        ax2.set_title('Cumulative Distribution', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 100)
        
        # Set same x-axis labels
        ax2.set_xticks(range(len(top_data)))
        ax2.set_xticklabels(price_labels, rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
        img_buffer.seek(0)
        plt.close()
        
        return img_buffer, "Flow chart generated successfully"