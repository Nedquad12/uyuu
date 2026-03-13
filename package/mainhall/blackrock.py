import sys
sys.path.append ("/home/ec2-user/package/machine")
from blackrockmain import Blackrock
from imporh import *

viewer = Blackrock()

@is_authorized_user 
@spy      
@vip       
@with_queue_control
async def blackrock_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /all command to search ticker across all BlackRock regions"""
    
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ Format: /all <TICKER>\nContoh: /all BBRI")
        return
    
    ticker = parts[1].upper()
    
    # Load data for all regions
    await update.message.reply_text("🔄 Searching across all Manager Invesment...")
    
    found_regions = []
    results = []
    
    try:
        for region in viewer.blackrock_folders.keys():
            viewer.load_blackrock_data_for_region(region)
            
            if viewer.blackrock_data[region] is None:
                continue
            
            # Format ticker based on region requirements
            formatted_ticker = format_ticker_for_region(ticker, region)
            
            # Search for ticker in this region
            ticker_data = viewer.search_blackrock_ticker(region, formatted_ticker)
            
            if ticker_data is not None:
                found_regions.append(region)
                
                try:
                    chart_buffer, caption = viewer.create_blackrock_chart(region, formatted_ticker)
                    if chart_buffer is not None:
                        results.append({
                            'region': region,
                            'chart_buffer': chart_buffer,
                            'caption': caption,
                            'ticker': formatted_ticker
                        })
                except Exception as e:
                    continue
        
        if not results:
            await update.message.reply_text(f"❌ Ticker {ticker} tidak ditemukan di semua Manager Investasi")
            return
        
        # Send summary first
        summary = f"📊 Found {ticker} in {len(results)} regions:\n"
        for result in results:
            company_name = viewer.company_names.get(result['region'], 'BlackRock')
            summary += f"✅ {company_name} ({result['region'].upper()})\n"
        
        await update.message.reply_text(summary)
        
        # Send charts for each region
        for result in results:
            try:
                await update.message.reply_photo(
                    photo=result['chart_buffer'],
                    caption=result['caption']
                )
                # Small delay between messages to avoid rate limiting
                await asyncio.sleep(0.5)
            except Exception as e:
                company_name = viewer.company_names.get(result['region'], 'BlackRock')
                await update.message.reply_text(f"❌ Error sending {company_name} chart: {str(e)}")
        
        # Clean up data
        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error mencari Manager Investasi: {str(e)}")

def format_ticker_for_region(ticker, region):
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


@is_authorized_user
@spy
@with_queue_control
@with_rate_limit 
async def blackrock_btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    viewer.load_blackrock_data_for_region('btc')
    
    # Bitcoin only - tidak perlu ticker
    if viewer.blackrock_data['btc'] is None:
        await update.message.reply_text("❌ Tidak ada data Bitcoin di server, beritahu admin @Rendanggedang atau https://x.com/saberial_link/.")
        return
    try:
        # Assume Bitcoin ticker for BTC
        chart_buffer, caption = viewer.create_blackrock_chart('btc', 'BTC')
        if chart_buffer is None:
            await update.message.reply_text("❌ Tidak ada data Bitcoin di server, beritahu admin @Rendanggedang atau https://x.com/saberial_link/")
            return
        
        await update.message.reply_photo(
        photo=chart_buffer,
        caption=caption
        )
        viewer.blackrock_data['btc'] = None
        
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal membuat chart, server overload: {str(e)}")
  
@is_authorized_user   
@spy    
@vip       
@with_queue_control
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
                'indonesia': 'BK',
                'dim': 'DIM', 
                'btc': 'BTC',
                'spdr': 'SPD',
                'jp': 'JPN',
                'x': 'X',
                'gs': 'GS',
                'sch': 'SCH',
                'ws': 'WS',
                'inv': 'INV',
                'fid': 'FID',
                'col': 'COL',
                'ksa': 'KSA'
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
            'indonesia': None,
            'btc': None,
            'dim': None,
            'spdr': None,
            'jp': None,
            'x': None,
            'gs': None,
            'sch': None,
            'ws': None,
            'inv': None,
            'fid': None,
            'col': None,
            'ksa': None
        }

        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting significant movements: {str(e)}")
        
        # Also clear data on error
        viewer.blackrock_data = {
            'indonesia': None,
            'btc': None,
            'dim': None,
            'spdr': None,
            'jp': None,
            'x': None,
            'gs': None,
            'sch': None,
            'ws': None,
            'inv': None,
            'fid': None,
            'col': None,
            'ksa': None
        }

        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting significant movements: {str(e)}")
        
        # Also clear data on error
        viewer.blackrock_data = {
            'indonesia': None,
            'btc': None,
            'dim': None,
            'spdr': None,
            'jp': None,
            'x': None,
            'gs': None,
            'sch': None,
            'ws': None,
            'inv': None,
            'fid': None,
            'col': None,
            'ksa': None
        }

        for region in viewer.blackrock_folders.keys():
            viewer.blackrock_data[region] = None

@is_authorized_user
@spy    
@vip  
@with_queue_control
async def blackrock_indonesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await handle_blackrock_command(update, context, 'indonesia')

@is_authorized_user
@spy 
@vip 
@with_queue_control
async def blackrock_dim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await handle_blackrock_command(update, context, 'dim')
 
@is_authorized_user 
@spy        
@with_queue_control
@with_rate_limit 
async def blackrock_spdr(update: Update, context: ContextTypes.DEFAULT_TYPE):

    
    await handle_blackrock_command(update, context, 'spdr')

@is_authorized_user
@spy
@with_queue_control
@with_rate_limit 
async def blackrock_jp(update: Update, context: ContextTypes.DEFAULT_TYPE):
 
    await handle_blackrock_command(update, context, 'jp')
 
@is_authorized_user 
@spy          
@with_queue_control
@with_rate_limit 
async def blackrock_x(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await handle_blackrock_command(update, context, 'x')
 
@is_authorized_user 
@spy           
@with_queue_control
@with_rate_limit 
async def blackrock_gs(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await handle_blackrock_command(update, context, 'gs')

@is_authorized_user 
@spy         
@with_queue_control
@with_rate_limit 
async def blackrock_sch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await handle_blackrock_command(update, context, 'sch')

@is_authorized_user 
@spy      
@with_queue_control
@with_rate_limit 
async def blackrock_fid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    await handle_blackrock_command(update, context, 'fid')

@is_authorized_user  
@spy
@with_queue_control
@with_rate_limit 
async def blackrock_ws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_blackrock_command(update, context, 'ws')
    
@is_authorized_user  
@spy 
@with_queue_control
@with_rate_limit 
async def blackrock_col(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_blackrock_command(update, context, 'col')
    
@is_authorized_user  
@spy 
@with_queue_control
@with_rate_limit 
async def blackrock_ksa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_blackrock_command(update, context, 'ksa')

@is_authorized_user 
@spy        
@with_queue_control
@with_rate_limit 
async def blackrock_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):

    
    await handle_blackrock_command(update, context, 'inv')

        
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
        
    if region == 'dim':
        if not ticker.endswith(' IJ'):
            ticker = f"{ticker} IJ"
            
    if region == 'x':
        if not ticker.endswith(' IJ'):
            ticker = f"{ticker} IJ"
            
    if region == 'ws':
        if not ticker.endswith(' IJ'):
            ticker = f"{ticker} IJ"
            
    if region == 'fid':
        if not ticker.endswith('.IJ'):
            ticker = f"{ticker}.IJ"
            
    if region == 'inv':
        if not ticker.endswith(' IJ'):
            ticker = f"{ticker} IJ"        
    
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