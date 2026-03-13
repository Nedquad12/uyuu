import pandas as pd
import numpy as np
from datetime import datetime
import logging
import sys
sys.path.append("/home/ec2-user/package/machine")
from ma_tracker import ma_tracker

logger = logging.getLogger(__name__)

class TightTracker:
    """Tracker untuk saham dengan MA yang tight (rapat)"""
    
    def __init__(self):
        self.ma_tracker = ma_tracker
    
    def calculate_distance_from_ma(self, close_price, ma_value):
        """Calculate percentage distance from MA"""
        if ma_value == 0 or pd.isna(ma_value):
            return float('inf')
        return ((close_price - ma_value) / ma_value) * 100
    
    def find_very_tight_stocks(self):
        """
        Find stocks that are:
        1. Above MA3, MA5, MA10, MA20
        2. Within 5% from ALL these MAs
        """
        results = []
        
        if not self.ma_tracker.ma_cache:
            logger.warning("MA cache is empty. Please run /reload2 first")
            return results
        
        for stock_code, stock_data in self.ma_tracker.ma_cache.items():
            try:
                close = stock_data.get('close')
                volume = stock_data.get('volume', 0)
                
                # Get MA values from mas dict
                mas = stock_data.get('mas', {})
                ma3 = mas.get(3)
                ma5 = mas.get(5)
                ma10 = mas.get(10)
                ma20 = mas.get(20)
                
                # Skip if any data is missing
                if any(x is None for x in [close, ma3, ma5, ma10, ma20]):
                    continue
                
                if any(pd.isna(x) or x == 0 for x in [close, ma3, ma5, ma10, ma20]):
                    continue
                
                # Check if close is above all MAs
                if not (close > ma3 and close > ma5 and close > ma10 and close > ma20):
                    continue
                
                # Calculate distance from each MA
                dist_ma3 = self.calculate_distance_from_ma(close, ma3)
                dist_ma5 = self.calculate_distance_from_ma(close, ma5)
                dist_ma10 = self.calculate_distance_from_ma(close, ma10)
                dist_ma20 = self.calculate_distance_from_ma(close, ma20)
                
                # Check if within 5% from ALL MAs
                if all(dist < 5.0 for dist in [dist_ma3, dist_ma5, dist_ma10, dist_ma20]):
                    # Calculate value in billions
                    value_billion = (close * volume) / 1_000_000_000
                    
                    # Filter: only include if value >= 0.5 billion
                    if value_billion >= 0.5:
                        results.append({
                            'code': stock_code,
                            'close': close,
                            'ma20': ma20,
                            'volume': volume,
                            'value': value_billion,
                            'max_distance': max(dist_ma3, dist_ma5, dist_ma10, dist_ma20)
                        })
            
            except Exception as e:
                logger.error(f"Error processing {stock_code}: {e}")
                continue
        
        # Sort by value (descending - highest value first)
        results.sort(key=lambda x: x['value'], reverse=True)
        
        return results
    
    def find_tight_stocks(self):
        """
        Find stocks that are:
        1. Above MA3, MA5, MA10, MA20
        2. Within 5-7% from ALL these MAs
        """
        results = []
        
        if not self.ma_tracker.ma_cache:
            logger.warning("MA cache is empty. Please run /reload2 first")
            return results
        
        for stock_code, stock_data in self.ma_tracker.ma_cache.items():
            try:
                close = stock_data.get('close')
                volume = stock_data.get('volume', 0)
                
                # Get MA values from mas dict
                mas = stock_data.get('mas', {})
                ma3 = mas.get(3)
                ma5 = mas.get(5)
                ma10 = mas.get(10)
                ma20 = mas.get(20)
                
                # Skip if any data is missing
                if any(x is None for x in [close, ma3, ma5, ma10, ma20]):
                    continue
                
                if any(pd.isna(x) or x == 0 for x in [close, ma3, ma5, ma10, ma20]):
                    continue
                
                # Check if close is above all MAs
                if not (close > ma3 and close > ma5 and close > ma10 and close > ma20):
                    continue
                
                # Calculate distance from each MA
                dist_ma3 = self.calculate_distance_from_ma(close, ma3)
                dist_ma5 = self.calculate_distance_from_ma(close, ma5)
                dist_ma10 = self.calculate_distance_from_ma(close, ma10)
                dist_ma20 = self.calculate_distance_from_ma(close, ma20)
                
                max_dist = max(dist_ma3, dist_ma5, dist_ma10, dist_ma20)
                min_dist = min(dist_ma3, dist_ma5, dist_ma10, dist_ma20)
                
                # Check if within 5-7% range from ALL MAs
                # All distances must be >= 5% and < 7%
                if all(5.0 <= dist < 7.0 for dist in [dist_ma3, dist_ma5, dist_ma10, dist_ma20]):
                    # Calculate value in billions
                    value_billion = (close * volume) / 1_000_000_000
                    
                    # Filter: only include if value >= 0.5 billion
                    if value_billion >= 0.5:
                        results.append({
                            'code': stock_code,
                            'close': close,
                            'ma20': ma20,
                            'volume': volume,
                            'value': value_billion,
                            'max_distance': max_dist
                        })
            
            except Exception as e:
                logger.error(f"Error processing {stock_code}: {e}")
                continue
        
        # Sort by value (descending - highest value first)
        results.sort(key=lambda x: x['value'], reverse=True)
        
        return results
    
    def format_very_tight_results(self, results):
        """Format very tight results in monospace table"""
        if not results:
            return "Tidak ada saham yang memenuhi kriteria Very Tight"
        
        message = "```\n"
        message += "Very Tight Stocks\n"
        message += "Value minimal 0.5 Miliar\n\n"
        
        # Header
        message += f"{'Kode':<6} {'Close':>8} {'MA20':>8} {'Volume':>10} {'Value':>8}\n"
        message += "-" * 48 + "\n"
        
        # Data rows
        for stock in results:
            volume_million = stock['volume'] / 1_000_000
            volume_str = f"{volume_million:.0f}" if volume_million >= 1 else f"{volume_million:.1f}"
            value_str = f"{stock['value']:.0f}" if stock['value'] >= 1 else f"{stock['value']:.1f}"
            
            message += f"{stock['code']:<6} "
            message += f"{stock['close']:>8.0f} "
            message += f"{stock['ma20']:>8.0f} "
            message += f"{volume_str:>10} "
            message += f"{value_str:>8}\n"
        
        message += f"\nTotal: {len(results)} saham\n"
        message += "Volume dalam Juta, Value dalam Miliar Rupiah\n"
        message += "```"
        
        return message
    
    def format_tight_results(self, results):
        """Format tight results in monospace table"""
        if not results:
            return "Tidak ada saham yang memenuhi kriteria Tight"
        
        message = "```\n"
        message += "Tight Stocks\n"
        message += "Value minimal 0.5 Miliar\n\n"
        
        # Header
        message += f"{'Kode':<6} {'Close':>8} {'MA20':>8} {'Volume':>10} {'Value':>8}\n"
        message += "-" * 48 + "\n"
        
        # Data rows
        for stock in results:
            volume_million = stock['volume'] / 1_000_000
            volume_str = f"{volume_million:.0f}" if volume_million >= 1 else f"{volume_million:.1f}"
            value_str = f"{stock['value']:.0f}" if stock['value'] >= 1 else f"{stock['value']:.1f}"
            
            message += f"{stock['code']:<6} "
            message += f"{stock['close']:>8.0f} "
            message += f"{stock['ma20']:>8.0f} "
            message += f"{volume_str:>10} "
            message += f"{value_str:>8}\n"
        
        message += f"\nTotal: {len(results)} saham\n"
        message += "Volume dalam Juta, Value dalam Miliar Rupiah\n"
        message += "```"
        
        return message

# Singleton instance
tight_tracker = TightTracker()
