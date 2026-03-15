import logging as logger
from telegram import Update
from datetime import datetime
from telegram.ext import ContextTypes
import matplotlib.pyplot as plt
import gc
import glob
import pandas as pd
import os
import io
import matplotlib.dates as mdates

class TelegramStockDataViewer:
    def __init__(self, data_folder=None):
        self.margin_folder = "/home/ec2-user/database/margin"
        self.margin_df = None
        self.margin_fields = ['Volume', 'Nilai', 'Frekuensi']

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
            
    def search_margin_stock(self, code):
        """Search margin data for specific stock"""
        if self.margin_df is None:
            return None
    
        stock_data = self.margin_df[self.margin_df['Kode Saham'].str.upper() == code.upper()]
        return stock_data if not stock_data.empty else None
    
    def get_data_info(self):
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
            'margin': margin_info
        }   
        
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
            
viewer = TelegramStockDataViewer()

  
async def margin_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /m"""
    
    viewer.load_margin_files()
   
    if viewer.margin_df is None:
        await update.message.reply_text( "❌ No margin data loaded. Saham ini tidak terdaftar dalam margin.")
        return
    
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Maskan kode saham.\nContoh: `/m BBCA`", parse_mode='Markdown')
        return
    code = parts[1].upper()
    
    try:
        chart_buffer = viewer.create_margin_charts(code)
        if chart_buffer is None:
            await update.message.reply_text(f"❌ Saham ini tidak termasuk daftar Margin: {code}")
            return
        
        # Send chart
        await update.message.reply_photo(
        photo=chart_buffer,
        caption=f"📊 Transaction Margin for {code}"
        )
        
        viewer.margin_df = None
        plt.close('all')
        gc.collect()
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error creating margin chart: {str(e)}")
        logger.error(f"Error creating margin chart: {e}")

