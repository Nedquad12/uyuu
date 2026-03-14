

def format_as_code_block(text: str) -> str:
    return f"```\n{text.strip()}\n```"

viewer = TelegramStockDataViewer()

@is_authorized_user
@spy
@with_queue_control  
@with_rate_limit       
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

@is_authorized_user    
@spy    
@with_queue_control
async def export_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /ex"""
 
    viewer.load_all_excel_files()
  
    if viewer.combined_df is None:
        await update.message.reply_text("❌ Tidak ada data. Beritahu admin @Rendanggedang bahwa server bermaslah")
        return
    
    # Extract stock code from command
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Masukan kode saham\nContoh: /export BBCA")
        return
    
    code = parts[1].upper()
    
    # Search for stock
    stock_data = viewer.search_stock(code)
    
    if stock_data is None:
        await update.message.reply_text(f"❌ Tidak ada data untuk: {code}")
        return
    
    try:
        # Create Excel report
        export_file = f"export_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        viewer.create_excel_report(stock_data, export_file, code)
        
        # Send file
        with open(export_file, 'rb') as f:
             await update.message.reply_document(
             document=f,
             caption=f"📊 Stock analysis for {code}\n\n📋 Sheet 'Shares': Data dalam lembar saham\n💰 Sheet 'Value': Data dalam Rupiah (lembar × harga terbaru) + Ownership %\n\nKategori: IS=Asuransi, CP=Korporat, PF=Dana Pensiun, IB=Bank, ID=Individu, MF=Reksadana, SC=Sekuritas, FD=Foundation, OT=Others"
         )
        # Clean up
        os.remove(export_file)
        viewer.combined_df = None        
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error creating Excel report: {str(e)}")
        logger.error(f"Error creating Excel report: {e}")
        
@is_authorized_user
@spy
@with_queue_control
async def asing_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /asing"""
    parts = update.message.text.strip().split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Masukkan kode saham.\nContoh: `/asing BBCA`", parse_mode='Markdown')
        return

    code = parts[1].upper()
    viewer.load_watchlist_data()
    summary = viewer.get_foreign_summary_by_days(code)

    if not summary:
        await update.message.reply_text(f"❌ Tidak ditemukan data asing untuk: {code}")
        return

    msg_lines = [f"📊 Data Pembelian & Penjualan Asing: {code}. Data dalam bentuk lembar saham\n"]
    msg_lines.append(f"{'Hari':>5} | {'Buy':>12} | {'Sell':>12} | {'Net':>13}")
    msg_lines.append("-" * 47)
    for days, buy, sell, net in summary:
        msg_lines.append(f"{days:>5} | {buy:>12,.0f} | {sell:>12,.0f} | {net:>+13,.0f}")

    await update.message.reply_text(f"```\n" + "\n".join(msg_lines) + "\n```", parse_mode='Markdown')
