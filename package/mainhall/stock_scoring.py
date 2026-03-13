from imporh import *
import logging
import asyncio
from rate_limiter import with_rate_limit
from utils import is_authorized_user
from state import with_queue_control, vip, spy

# Import dengan try-except untuk debugging
try:
    from stock_summary import collect_stock_data
    print("✅ collect_stock_data berhasil diimport")
except ImportError as e:
    print(f"❌ ERROR: Tidak bisa import collect_stock_data: {e}")
    # Fallback function jika import gagal
    async def collect_stock_data(stock_code):
        return {}

try:
    from saham_unified import (
        analyze_stock_volume,
        get_stock_ma_data,
        get_foreign_summary_by_days,
        get_holdings_summary_fast
    )
    print("✅ saham_unified berhasil diimport")
except ImportError as e:
    print(f"❌ ERROR: Tidak bisa import dari saham_unified: {e}")

logger = logging.getLogger(__name__)

class StockScorer:
    """Class untuk menghitung skor saham berdasarkan berbagai indikator"""
    
    def __init__(self):
        self.scores = {}
        self.details = {}
    
    def calculate_vsa_score(self, vol_spike):
        """
        VSA Score:
        - > 1.0 = +2
        - > 0.7 = +1
        - <= 0.7 = -1
        """
        try:
            spike = float(vol_spike)
            if spike > 1.0:
                return 2, f"VSA {spike:.2f} (>1.0) = +2"
            elif spike > 0.7:
                return 1, f"VSA {spike:.2f} (>0.7) = +1"
            else:
                return -1, f"VSA {spike:.2f} (≤0.7) = -1"
        except:
            return 0, "VSA data tidak tersedia = 0"
    
    def calculate_ma_score(self, ma_analysis):
        """
        MA Score:
        - 4 MA above = +2
        - 3 MA above = +1
        - < 3 MA above = -1
        """
        try:
            if not ma_analysis or 'mas' not in ma_analysis:
                return 0, "MA data tidak tersedia = 0"
            
            ma_periods = [20, 60, 120, 200]
            above_count = sum(
                1 for p in ma_periods 
                if ma_analysis['mas'].get(p) and ma_analysis['mas'][p]['position'] == "ABOVE"
            )
            
            if above_count == 4:
                return 2, f"MA {above_count}/4 Above = +2"
            elif above_count == 3:
                return 1, f"MA {above_count}/4 Above = +1"
            else:
                return -1, f"MA {above_count}/4 Above = -1"
        except Exception as e:
            logger.error(f"Error calculating MA score: {e}")
            return 0, "MA error = 0"
    
    def calculate_foreign_score(self, foreign_summary):
        """
        Foreign Flow Score:
        - 1H, 5H, 1B positif = +2
        - 5H, 1B positif = +1
        - Hanya 1H positif = 0
        - Semua negatif = -1
        """
        try:
            if not foreign_summary:
                return 0, "Foreign data tidak tersedia = 0"
            
            # Extract net values untuk 1H, 5H, 1B
            periods = {}
            for period_name, buy, sell, net in foreign_summary:
                periods[period_name] = net
            
            h1 = periods.get('1H', 0) > 0
            h5 = periods.get('5H', 0) > 0
            b1 = periods.get('1B', 0) > 0
            
            if h1 and h5 and b1:
                return 2, "Foreign 1H+5H+1B positif = +2"
            elif h5 and b1:
                return 1, "Foreign 5H+1B positif = +1"
            elif h1:
                return 0, "Foreign hanya 1H positif = 0"
            else:
                return -1, "Foreign semua negatif = -1"
        except Exception as e:
            logger.error(f"Error calculating foreign score: {e}")
            return 0, "Foreign error = 0"
    
    def calculate_holdings_score(self, holdings_data):
        """
        Holdings Score:
        - Ritel bertambah (% positif) = -1
         - Ritel berkurang (% negatif) = +1
        """
        try:
            if not holdings_data:
                return 0, "Holdings tidak tersedia = 0"
        
            import re
        
        # Cari baris yang mengandung "Ritel" dan extract persentase
            ritel_changes = []
            lines = str(holdings_data).split('\n')
        
            for line in lines:
                if 'Ritel' in line or 'ritel' in line.lower():
                # Pattern untuk menangkap persentase: (+5.2%) atau (-3.1%)
                    match = re.search(r'\(([+-]?\d+\.?\d*)%\)', line)
                    if match:
                        try:
                            percentage = float(match.group(1))
                            ritel_changes.append(percentage)
                        except ValueError:
                            continue
        
            if ritel_changes:
            # Ambil perubahan terakhir (bulan terbaru)
                last_change = ritel_changes[-1]
            
                if last_change > 0:
                   return -1, f"Ritel naik {last_change:+.1f}% = -1"
                elif last_change < 0:
                   return 1, f"Ritel turun {last_change:+.1f}% = +1"
                else:
                   return 0, "Ritel flat 0.0% = 0"
        
        # Jika tidak menemukan data Ritel
            return 0, "Data Ritel tidak ditemukan = 0"
        
        except Exception as e:
            logger.error(f"Error calculating holdings score: {e}")
            return 0, "Holdings error = 0"
    
    def calculate_indicator_scores(self, data):
        """
        Indikator dari stock_summary:
        - FSA: ada = +1, kosong = -1
        - VSA: ada = +1, kosong = -1
        - M: M+ = +2, M- = -1, kosong = +1
        - S: S+ = +2, S- = -1, kosong = +1
        - FS: R = +2, x = +1, kosong = 0
        - VT/T: ada = +2, kosong = -1
        - IP: 4,3 = +2; 2,1 = +1; 0 = 0; -1,-2 = -1; -3,-4 = -2
        """
        scores = {}
        details = {}
        
        # FSA
        fsa = data.get('fsa', '-')
        if fsa != '-':
            scores['fsa'] = 1
            details['fsa'] = f"FSA {fsa} = +1"
        else:
            scores['fsa'] = -1
            details['fsa'] = "FSA kosong = -1"
        
        # VSA (dari indikator, beda dengan VSA score di atas)
        vsa = data.get('vsa', '-')
        if vsa != '-':
            scores['vsa_ind'] = 1
            details['vsa_ind'] = f"VSA {vsa} = +1"
        else:
            scores['vsa_ind'] = -1
            details['vsa_ind'] = "VSA kosong = -1"
        
        # M (MACD)
        m = data.get('m', '-')
        if m == 'M+':
            scores['m'] = 2
            details['m'] = "M+ = +2"
        elif m == 'M-':
            scores['m'] = 1
            details['m'] = "M- = -1"
        else:
            scores['m'] = -1
            details['m'] = f"M {m} = +1"
        
        # S (Stochastic)
        s = data.get('s', '-')
        if s == 'S+':
            scores['s'] = 2
            details['s'] = "S+ = +2"
        elif s == 'S-':
            scores['s'] = 1
            details['s'] = "S- = -1"
        else:
            scores['s'] = -1
            details['s'] = f"S {s} = +1"
        
        # FS (Foreign Spike)
        fs = data.get('fs', '-')
        if 'R' in str(fs):
            scores['fs'] = 2
            details['fs'] = f"FS {fs} (Reversal) = +2"
        elif 'x' in str(fs) or fs != '-':
            scores['fs'] = 1
            details['fs'] = f"FS {fs} = +1"
        else:
            scores['fs'] = 0
            details['fs'] = "FS kosong = 0"
        
        # VT/T
        vt_t = data.get('vt_t', '-')
        if vt_t != '-':
            scores['vt_t'] = 1
            details['vt_t'] = f"{vt_t} = +2"
        else:
            scores['vt_t'] = -1
            details['vt_t'] = "VT/T kosong = -1"
        
        # IP (Indicator Point)
        ip = data.get('ipd', '-')
        try:
            if ip != '-':
                ip_val = int(ip)
                if ip_val in [3, 4]:
                    scores['ip'] = 2
                    details['ip'] = f"IP {ip_val} = +2"
                elif ip_val in [1, 2]:
                    scores['ip'] = 1
                    details['ip'] = f"IP {ip_val} = +1"
                elif ip_val == 0:
                    scores['ip'] = 0
                    details['ip'] = "IP 0 = 0"
                elif ip_val in [-1, -2]:
                    scores['ip'] = -1
                    details['ip'] = f"IP {ip_val} = -1"
                elif ip_val in [-3, -4]:
                    scores['ip'] = -2
                    details['ip'] = f"IP {ip_val} = -2"
                else:
                    scores['ip'] = 0
                    details['ip'] = f"IP {ip_val} = 0"
            else:
                scores['ip'] = 0
                details['ip'] = "IP tidak tersedia = 0"
        except:
            scores['ip'] = 0
            details['ip'] = "IP error = 0"
        
        return scores, details
    
    async def calculate_total_score(self, stock_code):
        """Calculate total score untuk saham"""
        try:
            # 1. Get data dari stock_summary
            logger.info(f"Getting summary data for {stock_code}")
            summary_data = await collect_stock_data(stock_code)
            
            # 2. Get data dari saham_unified
            logger.info(f"Getting volume analysis for {stock_code}")
            volume_analysis, _ = analyze_stock_volume(stock_code)
            
            logger.info(f"Getting MA analysis for {stock_code}")
            ma_analysis, _ = get_stock_ma_data(stock_code)
            
            logger.info(f"Getting foreign summary for {stock_code}")
            foreign_summary = get_foreign_summary_by_days(stock_code)
            
            # Holdings analysis (async) dengan timeout lebih panjang
            holdings_data = None
            try:
                logger.info(f"Getting holdings data for {stock_code}")
                holdings_result = await asyncio.wait_for(
                    get_holdings_summary_fast(stock_code), 
                    timeout=10  # Tambah timeout jadi 10 detik
                )
                holdings_data, _ = holdings_result
            except asyncio.TimeoutError:
                logger.warning(f"Holdings data timeout for {stock_code}")
            except Exception as e:
                logger.error(f"Holdings data error for {stock_code}: {e}")
            
            # Calculate scores
            total_score = 0
            all_details = []
            
            # VSA Score (dari volume analysis)
            if volume_analysis:
                vsa_score, vsa_detail = self.calculate_vsa_score(volume_analysis['vol_spike'])
                total_score += vsa_score
                all_details.append(vsa_detail)
            
            # MA Score
            ma_score, ma_detail = self.calculate_ma_score(ma_analysis)
            total_score += ma_score
            all_details.append(ma_detail)
            
            # Foreign Score
            foreign_score, foreign_detail = self.calculate_foreign_score(foreign_summary)
            total_score += foreign_score
            all_details.append(foreign_detail)
            
            # Holdings Score
            holdings_score, holdings_detail = self.calculate_holdings_score(holdings_data)
            total_score += holdings_score
            all_details.append(holdings_detail)
            
            # Indicator Scores
            ind_scores, ind_details = self.calculate_indicator_scores(summary_data)
            for score in ind_scores.values():
                total_score += score
            for detail in ind_details.values():
                all_details.append(detail)
            
            return total_score, all_details, summary_data
            
        except Exception as e:
            logger.error(f"Error calculating total score for {stock_code}: {e}", exc_info=True)
            return None, None, None


# VERSI SEDERHANA UNTUK DEBUGGING
@is_authorized_user
@spy
@with_queue_control
@with_rate_limit 
async def stock_score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler untuk /ss - Stock Scoring"""
    
    try:
        # Log untuk debugging
        logger.info(f"Command /ss dipanggil oleh user {update.effective_user.id}")
        
        if not context.args:
            await update.message.reply_text(
                "Format: /ss <KODE_SAHAM>\nContoh: /ss BBCA"
            )
            return
        
        stock_code = context.args[0].upper().strip()
        logger.info(f"Processing stock: {stock_code}")
        
        processing_msg = await update.message.reply_text(
            f"🔍 Menghitung skor untuk {stock_code}... Mohon tunggu...",
            parse_mode='Markdown'
        )
        
        try:
            scorer = StockScorer()
            total_score, details, summary_data = await scorer.calculate_total_score(stock_code)
            
            if total_score is None:
                await processing_msg.edit_text(
                    "❌ Gagal menghitung skor. Silakan coba lagi."
                )
                return
            
            # Format output
            message = f"*📊 STOCK SCORING: {stock_code}*\n\n"
            
            # Show summary data
            message += "```\n"
            message += f"Close  : {summary_data.get('close', '-')}\n"
            message += f"FSA    : {summary_data.get('fsa', '-')}\n"
            message += f"VSA    : {summary_data.get('vsa', '-')}\n"
            message += f"M      : {summary_data.get('m', '-')}\n"
            message += f"S      : {summary_data.get('s', '-')}\n"
            message += f"FS     : {summary_data.get('fs', '-')}\n"
            message += f"VT/T   : {summary_data.get('vt_t', '-')}\n"
            message += f"IP     : {summary_data.get('ipd', '-')}\n"
            message += "```\n\n"
            
            # Show scoring breakdown
            message += "*Breakdown Skor:*\n"
            for detail in details:
                message += f"• {detail}\n"
            
            message += f"\n{'='*30}\n"
            message += f"*TOTAL SCORE: {total_score:+d}*\n"
            message += f"{'='*30}\n\n"
            
            # Interpretation
            if total_score >= 10:
                message += "🟢 *SANGAT BULLISH* - Strong buy signal!"
            elif total_score >= 5:
                message += "🟢 *BULLISH* - Good buy opportunity"
            elif total_score >= 0:
                message += "🟡 *NETRAL* - Wait and see"
            elif total_score >= -5:
                message += "🔴 *BEARISH* - Caution advised"
            else:
                message += "🔴 *SANGAT BEARISH* - Avoid or short"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            await processing_msg.delete()
            
        except Exception as e:
            logger.error(f"Error in calculation for {stock_code}: {e}", exc_info=True)
            await processing_msg.edit_text(
                f"❌ Terjadi kesalahan saat menghitung skor.\n"
                f"Error: {str(e)}\n"
                f"Silakan hubungi admin jika masalah berlanjut."
            )
    
    except Exception as e:
        logger.error(f"Error in stock_score_command: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {str(e)}\n"
            "Silakan hubungi admin."
        )
