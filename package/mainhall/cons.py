import sys
sys.path.append("/home/ec2-user/package/machine")
from utama import TelegramStockDataViewer
from imporh import *
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

viewer = TelegramStockDataViewer()

# Mapping untuk nama kategori
CATEGORY_NAMES = {
    'IS': 'Asuransi',
    'CP': 'Korporat',
    'PF': 'Dana Pensiun',
    'IB': 'Bank',
    'ID': 'Individu',
    'MF': 'Reksadana',
    'SC': 'Sekuritas',
    'FD': 'Dana',
    'OT': 'Lainnya'
}

def create_ownership_chart(df: pd.DataFrame, code: str, category: str, investor_type: str) -> BytesIO:
    """Create line chart for ownership changes over time"""
    
    plt.figure(figsize=(12, 6))
    
    # Sort by date
    df = df.sort_values('Date')
    
    # Convert Date to datetime if needed
    if not pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = pd.to_datetime(df['Date'])
    
    # Plot
    plt.plot(df['Date'], df['Value'], marker='o', linewidth=2, markersize=8, color='#2E86AB')
    plt.fill_between(df['Date'], df['Value'], alpha=0.3, color='#2E86AB')
    
    # Formatting
    plt.title(f'{code} - {investor_type} {CATEGORY_NAMES.get(category, category)} Ownership', 
              fontsize=14, fontweight='bold', pad=20)
    plt.xlabel('Date', fontsize=11)
    plt.ylabel('Shares (Million)', fontsize=11)
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.gcf().autofmt_xdate()
    
    # Format y-axis to show values in millions
    ax = plt.gca()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M'))
    
    plt.tight_layout()
    
    # Save to buffer
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
    buffer.seek(0)
    plt.close()
    
    return buffer

def format_ownership_summary(df: pd.DataFrame, code: str, category: str, investor_type: str) -> str:
    """Format text summary of ownership changes"""
    
    # Sort by date
    df = df.sort_values('Date')
    
    category_name = CATEGORY_NAMES.get(category, category)
    
    lines = [f"📊 *{code} - {investor_type} {category_name}*\n"]
    lines.append(f"{'Date':<12} | {'Shares':>15} | {'Change':>15} | {'%':>8}")
    lines.append("-" * 60)
    
    prev_value = None
    first_value = None
    
    for idx, row in df.iterrows():
        date_str = row['Date'].strftime('%b %Y') if pd.api.types.is_datetime64_any_dtype(df['Date']) else str(row['Date'])
        value = row['Value']
        
        if first_value is None:
            first_value = value
        
        if prev_value is not None:
            change = value - prev_value
            pct_change = (change / prev_value * 100) if prev_value != 0 else 0
            change_str = f"{change:+,.0f}"
            pct_str = f"{pct_change:+.2f}%"
        else:
            change_str = "-"
            pct_str = "-"
        
        lines.append(f"{date_str:<12} | {value:>15,.0f} | {change_str:>15} | {pct_str:>8}")
        prev_value = value
    
    # Total change
    if len(df) > 0 and first_value is not None:
        total_change = df.iloc[-1]['Value'] - first_value
        total_pct = (total_change / first_value * 100) if first_value != 0 else 0
        lines.append("-" * 60)
        lines.append(f"\n📈 *Total Change:* {total_change:+,.0f} shares ({total_pct:+.2f}%)")
    
    return "```\n" + "\n".join(lines) + "\n```"

@is_authorized_user
@spy
@with_queue_control
@with_rate_limit
async def cons_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /cons - Show institutional ownership tracking"""
    
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Masukkan kode saham.\nContoh: `/cons BBCA`", 
            parse_mode='Markdown'
        )
        return
    
    code = parts[1].upper()
    
    # Store stock code in context
    context.user_data['cons_code'] = code
    
    # Create inline keyboard for Local/Foreign selection
    keyboard = [
        [
            InlineKeyboardButton("🏠 Local", callback_data=f"cons_local_{code}"),
            InlineKeyboardButton("🌍 Foreign", callback_data=f"cons_foreign_{code}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📊 Pilih tipe investor untuk *{code}*:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def cons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks for /cons"""
    
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Parse callback data
    if data.startswith('cons_local_') or data.startswith('cons_foreign_'):
        # First level: Local or Foreign
        parts = data.split('_')
        investor_type = parts[1].capitalize()  # 'Local' or 'Foreign'
        code = parts[2]
        
        # Store investor type
        context.user_data['cons_investor_type'] = investor_type
        context.user_data['cons_code'] = code
        
        # Create inline keyboard for category selection
        keyboard = [
            [
                InlineKeyboardButton("IS", callback_data=f"cons_cat_{investor_type}_IS_{code}"),
                InlineKeyboardButton("CP", callback_data=f"cons_cat_{investor_type}_CP_{code}"),
                InlineKeyboardButton("PF", callback_data=f"cons_cat_{investor_type}_PF_{code}"),
            ],
            [
                InlineKeyboardButton("IB", callback_data=f"cons_cat_{investor_type}_IB_{code}"),
                InlineKeyboardButton("ID", callback_data=f"cons_cat_{investor_type}_ID_{code}"),
                InlineKeyboardButton("MF", callback_data=f"cons_cat_{investor_type}_MF_{code}"),
            ],
            [
                InlineKeyboardButton("SC", callback_data=f"cons_cat_{investor_type}_SC_{code}"),
                InlineKeyboardButton("FD", callback_data=f"cons_cat_{investor_type}_FD_{code}"),
                InlineKeyboardButton("OT", callback_data=f"cons_cat_{investor_type}_OT_{code}"),
            ],
            [
                InlineKeyboardButton("« Back", callback_data=f"cons_back_{code}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📊 *{code}* - {investor_type}\nPilih kategori:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif data.startswith('cons_cat_'):
        # Second level: Category selection
        parts = data.split('_')
        investor_type = parts[2]  # 'Local' or 'Foreign'
        category = parts[3]  # 'IS', 'CP', etc.
        code = parts[4]
        
        await query.edit_message_text(f"⏳ Loading data for {code} - {investor_type} {category}...")
        
        try:
            # Load Excel files
            viewer.load_all_excel_files()
            
            if viewer.combined_df is None:
                await query.edit_message_text(
                    "❌ Tidak ada data. Beritahu admin @Rendanggedang bahwa server bermasalah"
                )
                return
            
            # Filter data for the stock
            stock_data = viewer.combined_df[viewer.combined_df['Code'] == code].copy()
            
            if stock_data.empty:
                await query.edit_message_text(f"❌ Tidak ada data untuk: {code}")
                viewer.combined_df = None
                return
            
            # Get column name
            col_name = f"{investor_type} {category}"
            
            if col_name not in stock_data.columns:
                await query.edit_message_text(f"❌ Kolom {col_name} tidak ditemukan dalam data")
                viewer.combined_df = None
                return
            
            # Prepare data for chart
            chart_df = stock_data[['Date', col_name]].copy()
            chart_df.columns = ['Date', 'Value']
            chart_df = chart_df.dropna()
            
            # Check if we have at least 3 data points
            if len(chart_df) < 3:
                await query.edit_message_text(
                    f"❌ Data tidak cukup untuk {code}. Minimal 3 bulan data diperlukan.\n"
                    f"Data tersedia: {len(chart_df)} bulan"
                )
                viewer.combined_df = None
                return
            
            # Create chart
            chart_buffer = create_ownership_chart(chart_df, code, category, investor_type)
            
            # Create summary text
            summary_text = format_ownership_summary(chart_df, code, category, investor_type)
            
            # Send chart and summary
            await query.message.reply_photo(
                photo=chart_buffer,
                caption=summary_text,
                parse_mode='Markdown'
            )
            
            # Delete the "Loading..." message
            await query.message.delete()
            
            # Cleanup
            viewer.combined_df = None
            plt.close('all')
            gc.collect()
            
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")
            logger.error(f"Error in cons_callback: {e}", exc_info=True)
            viewer.combined_df = None
    
    elif data.startswith('cons_back_'):
        # Back button
        code = data.split('_')[2]
        
        keyboard = [
            [
                InlineKeyboardButton("🏠 Local", callback_data=f"cons_local_{code}"),
                InlineKeyboardButton("🌍 Foreign", callback_data=f"cons_foreign_{code}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📊 Pilih tipe investor untuk *{code}*:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
