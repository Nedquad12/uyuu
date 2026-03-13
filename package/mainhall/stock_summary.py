from imporh import *
from freq import analyze_frequency_spike
from vol import get_vsa_from_cache  # FIXED: Ambil dari cache langsung
from ms_full import ms_tracker
from fspike import calculate_foreign_spike_with_vsa
from tight_tracker import tight_tracker
import logging
import sys
sys.path.append ("/home/ec2-user/package/machine")
from score_machine import ip_tracker

logger = logging.getLogger(__name__)

@is_authorized_user
@spy
@vip
@with_queue_control
async def stock3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /3 - Summary saham dari berbagai indikator"""
    
    # Validasi input
    if not context.args:
        await update.message.reply_text(
            "Format: /3 <KODE_SAHAM>\nContoh: /3 BBCA"
        )
        return
    
    stock_code = context.args[0].upper().strip()
    
    await update.message.reply_text(
        f"Mengumpulkan data untuk {stock_code}...",
        parse_mode='Markdown'
    )
    
    try:
        # Collect data from all modules
        data = await collect_stock_data(stock_code)
        
        # Format and send main output
        main_message = format_stock_summary(stock_code, data)
        await update.message.reply_text(main_message, parse_mode='Markdown')
        
        # Always send MA info
        ma_message = format_ma_info(stock_code, data)
        await update.message.reply_text(ma_message, parse_mode='Markdown')
        
         # Tambahan: kirim IP info
        ip_message = format_ip_info(stock_code, data)
        await update.message.reply_text(ip_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stock3_command for {stock_code}: {e}")
        await update.message.reply_text(
            "Terjadi kesalahan saat mengumpulkan data.\n"
            "Silakan hubungi admin jika masalah berlanjut."
        )


async def collect_stock_data(stock_code):
    """Collect data from all modules for a specific stock"""
    data = {
        'close': '-',
        'fsa': '-',
        'vsa': '-',
        'm': '-',
        's': '-',
        'fs': '-',
        'vt_t': '-',
        'ma_data': None,  # For MA details if VT/T
        # Tambahan untuk IP data
        'ip': '-',
        'chg': '-',
        'md': '-',
        'sd': '-',
        'ipd': '-'
    }
    
    # 1. Get FSA from freq.py
    try:
        freq_results = analyze_frequency_spike()
        for code, chg, freq, f60, fsa in freq_results:
            if code == stock_code:
                data['fsa'] = f"{fsa:.1f}"
                if data['close'] == '-':
                    # Get close price from freq if not available yet
                    # Note: freq doesn't have close, we'll get it from vol or ms
                    pass
                break
        else:
            logger.info(f"FSA data not found for {stock_code}")
    except Exception as e:
        logger.error(f"Error getting FSA for {stock_code}: {e}")
    
    # 2. Get VSA from vol.py - FIXED: Ambil dari cache langsung
    try:
        vsa_data = get_vsa_from_cache(stock_code)
        if vsa_data:
            data['vsa'] = f"{vsa_data['vsa']:.1f}"
            logger.info(f"VSA found for {stock_code}: {data['vsa']}")
        else:
            logger.info(f"VSA data not found for {stock_code} in cache")
    except Exception as e:
        logger.error(f"Error getting VSA for {stock_code}: {e}")
    
    # 3. Get MACD & Stochastic from ms_full.py
    try:
        if not ms_tracker.ms_cache:
            logger.warning(f"MS cache empty, call admin")
        else:
            if stock_code in ms_tracker.ms_cache:
                stock_ms = ms_tracker.ms_cache[stock_code]
                signals = stock_ms.get('signals', [])
                
                # Get close price
                data['close'] = f"{stock_ms['close']:.0f}"
                
                # Get M signal
                m_signals = [s for s in signals if s.startswith('M')]
                data['m'] = m_signals[0] if m_signals else '-'
                
                # Get S signal
                s_signals = [s for s in signals if s.startswith('S')]
                data['s'] = s_signals[0] if s_signals else '-'
            else:
                logger.info(f"MS data not found for {stock_code}")
    except Exception as e:
        logger.error(f"Error getting MS for {stock_code}: {e}")
    
    # 4. Get Foreign Spike from fspike.py
    try:
        positive_spikes, reversal_spikes, error = calculate_foreign_spike_with_vsa()
        
        if error:
            logger.warning(f"Foreign spike error: {error}")
        else:
            # Check positive spikes
            found = False
            if positive_spikes:
                for spike in positive_spikes:
                    if spike['kode'] == stock_code:
                        ratio = spike['spike_ratio']
                        if ratio == float('inf'):
                            data['fs'] = "INF+"
                        else:
                            data['fs'] = f"{ratio:.0f}x"
                        found = True
                        break
            
            # Check reversal spikes if not found in positive
            if not found and reversal_spikes:
                for spike in reversal_spikes:
                    if spike['kode'] == stock_code:
                        ratio = abs(spike['spike_ratio'])
                        if ratio == float('inf'):
                            data['fs'] = "INF-R"
                        else:
                            data['fs'] = f"{ratio:.0f}R"
                        found = True
                        break
            
            if not found:
                logger.info(f"Foreign spike data not found for {stock_code}")
    except Exception as e:
        logger.error(f"Error getting Foreign Spike for {stock_code}: {e}")
    
    # 5. Get VT/T from tight_full.py AND get MA data
    try:
        # Always try to get MA data from ma_tracker first
        if stock_code in tight_tracker.ma_tracker.ma_cache:
            stock_ma_data = tight_tracker.ma_tracker.ma_cache[stock_code]
            data['ma_data'] = {
                'close': stock_ma_data.get('close'),
                'mas': stock_ma_data.get('mas', {})
            }
        
        # Check VT first
        vt_results = tight_tracker.find_very_tight_stocks()
        for stock in vt_results:
            if stock['code'] == stock_code:
                data['vt_t'] = 'VT'
                # Update ma_data if not already set
                if not data['ma_data']:
                    data['ma_data'] = {
                        'close': stock['close'],
                        'mas': tight_tracker.ma_tracker.ma_cache.get(stock_code, {}).get('mas', {})
                    }
                break
        
        # Check T if not VT
        if data['vt_t'] == '-':
            t_results = tight_tracker.find_tight_stocks()
            for stock in t_results:
                if stock['code'] == stock_code:
                    data['vt_t'] = 'T'
                    # Update ma_data if not already set
                    if not data['ma_data']:
                        data['ma_data'] = {
                            'close': stock['close'],
                            'mas': tight_tracker.ma_tracker.ma_cache.get(stock_code, {}).get('mas', {})
                        }
                    break
        
        if data['vt_t'] == '-':
            logger.info(f"VT/T data not found for {stock_code}")
            
    except Exception as e:
        logger.error(f"Error getting VT/T for {stock_code}: {e}")
        
    # 6. Ambil Indicator Point (IP) dari score_machine
    try:
        ip_data = ip_tracker.get_stock(stock_code)
        if ip_data:
            data['ip'] = f"{ip_data['ipd']:+d}"
            data['chg'] = f"{ip_data['chg']:+.1f}%"
            data['md'] = f"{ip_data['md']:+d}"
            data['sd'] = f"{ip_data['sd']:+d}"
            data['ipd'] = f"{ip_data['ipd']:+d}"
    except Exception as e:
        logger.error(f"Error getting IP data for {stock_code}: {e}")

    
    # If close price still not available, try to get from ma_tracker
    if data['close'] == '-':
        try:
            if stock_code in tight_tracker.ma_tracker.ma_cache:
                close = tight_tracker.ma_tracker.ma_cache[stock_code].get('close')
                if close:
                    data['close'] = f"{close:.0f}"
        except Exception as e:
            logger.error(f"Error getting close price from ma_tracker for {stock_code}: {e}")
    
    return data


def format_stock_summary(stock_code, data):
    """Format stock summary in monospace table"""
    message = f"*Stock Summary: {stock_code}*\n\n"
    message += "```\n"
    message += f"{'Kode':<6} {'Close':>7} {'FSA':>6} {'VSA':>6} {'M':<5} {'S':<5} {'FS':>6} {'VT/T':<4} {'IP':>4}\n"
    message += "-" * 50 + "\n"
    
    # Format each field with proper alignment
    kode = stock_code[:6]
    close = data['close'] if len(data['close']) <= 7 else data['close'][:7]
    fsa = data['fsa'] if len(data['fsa']) <= 6 else data['fsa'][:6]
    vsa = data['vsa'] if len(data['vsa']) <= 6 else data['vsa'][:6]
    m = data['m'] if len(data['m']) <= 5 else data['m'][:5]
    s = data['s'] if len(data['s']) <= 5 else data['s'][:5]
    fs = data['fs'] if len(data['fs']) <= 6 else data['fs'][:6]
    vt_t = data['vt_t']
    ip = data['ip'] if len(str(data['ip'])) <= 4 else str(data['ip'])[:4]
    
    message += f"{kode:<6} {close:>7} {fsa:>6} {vsa:>6} {m:<5} {s:<5} {fs:>6} {vt_t:<4} {ip:>4}\n"
    message += "```\n\n"
    
    # Legend
    message += "*Keterangan:*\n"
    message += "- FSA = Frequency Spike Analysis\n"
    message += "- VSA = Volume Spike Analysis\n"
    message += "- M = MACD Signal (M+/M-)\n"
    message += "- S = Stochastic Signal (S+/S-)\n"
    message += "- FS = Foreign Spike (x=positif, R=reversal)\n"
    message += "- VT = Very Tight (<5% dari MA)\n"
    message += "- T = Tight (5-7% dari MA)\n"
    message += "- IP = Indicator Point\n"
    message += "- - = Data tidak tersedia"
    
    return message


def format_ma_info(stock_code, data):
    """Format MA information for all stocks"""
    
    # If no MA data available, try to get close price from main data
    if not data['ma_data']:
        close_str = data.get('close', '-')
        if close_str == '-':
            return f"*Detail MA untuk {stock_code} tidak tersedia*\n_Call admin_"
        
        # If we have close but no MA data
        return f"*Moving Average Info: {stock_code}*\n\n" \
               f"Close Price: {close_str}\n\n" \
               f"_Data MA tidak tersedia. Call admin._"
    
    ma_data = data['ma_data']
    close = ma_data.get('close')
    mas = ma_data.get('mas', {})
    
    if not close:
        return f"*Detail MA untuk {stock_code} tidak tersedia*"
    
    message = f"*Moving Average Info: {stock_code}*\n\n"
    message += "```\n"
    message += f"Close Price: {close:.0f}\n\n"
    
    if mas:
        message += f"{'MA':<6} {'Value':>10} {'Dist %':>8}\n"
        message += "-" * 26 + "\n"
        
        # Show MA3, MA5, MA10, MA20, MA60, MA120, MA200
        ma_periods = [3, 5, 10, 20, 60, 120, 200]
        for period in ma_periods:
            ma_value = mas.get(period)
            if ma_value and ma_value > 0:
                distance = ((close - ma_value) / ma_value) * 100
                message += f"MA{period:<4} {ma_value:>10.0f} {distance:>7.1f}%\n"
            else:
                message += f"MA{period:<4} {'N/A':>10} {'N/A':>8}\n"
    else:
        message += "Data MA tidak tersedia\n"
    
    message += "```\n\n"
    
    # Show VT/T status if available
    if data['vt_t'] != '-':
        message += f"*Status: {data['vt_t']}*"
    
    return message

def format_ip_info(stock_code, data):
    """Format detail Indicator Point"""
    if data.get('ipd', '-') == '-':
        return f"*Indicator Point (IP) untuk {stock_code} tidak tersedia*"

    msg = f"Kode: {stock_code}\n"
    msg += f"Chg: {data.get('chg', '-')}\n"
    msg += f"M: {data.get('md', '-')}\n"
    msg += f"S: {data.get('sd', '-')}\n"
    msg += f"IP: {data.get('ipd', '-')}"
    return f"```\n{msg}\n```"
