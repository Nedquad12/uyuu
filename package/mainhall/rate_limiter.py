from datetime import datetime, timedelta
from typing import Dict, Tuple
import asyncio
from functools import wraps
import sys
sys.path.append ("/home/ec2-user/package/admin")
from auth import is_vip_user, load_roles

class RateLimiter:
    def __init__(self):
        # Dictionary untuk menyimpan data rate limiting per user
        # Format: {user_id: {'count': int, 'reset_time': datetime}}
        self.user_limits: Dict[int, Dict] = {}
        
        # Konfigurasi rate limiting
        self.MAX_REQUESTS = 2
        self.COOLDOWN_HOURS = 20
        
        # Load user roles saat inisialisasi
        load_roles()
    
    def is_vip(self, user_id: int) -> bool:
        """Cek apakah user adalah VIP menggunakan sistem auth.py"""
        return is_vip_user(user_id)
        
    def _cleanup_expired_entries(self):
        """Membersihkan entri yang sudah expired untuk menghemat memori"""
        current_time = datetime.now()
        expired_users = []
        
        for user_id, data in self.user_limits.items():
            if current_time >= data['reset_time']:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.user_limits[user_id]
    
    def check_rate_limit(self, user_id: int) -> Tuple[bool, str]:
        """
        Cek apakah user masih bisa melakukan request
        
        Returns:
            Tuple[bool, str]: (is_allowed, message)
        """
        # VIP users tidak dibatasi
        if self.is_vip(user_id):
            return True, "👑 VIP Access: Unlimited requests"
        
        # Cleanup expired entries first
        self._cleanup_expired_entries()
        
        current_time = datetime.now()
        
        # Jika user belum ada dalam tracking, buat entry baru
        if user_id not in self.user_limits:
            reset_time = current_time + timedelta(hours=self.COOLDOWN_HOURS)
            self.user_limits[user_id] = {
                'count': 1,
                'reset_time': reset_time
            }
            return True, f"✅ Request berhasil! Sisa quota: {self.MAX_REQUESTS - 1}/{self.MAX_REQUESTS}"
        
        user_data = self.user_limits[user_id]
        
        # Jika sudah lewat masa cooldown, reset counter
        if current_time >= user_data['reset_time']:
            reset_time = current_time + timedelta(hours=self.COOLDOWN_HOURS)
            self.user_limits[user_id] = {
                'count': 1,
                'reset_time': reset_time
            }
            return True, f"✅ Request berhasil! Sisa quota: {self.MAX_REQUESTS - 1}/{self.MAX_REQUESTS}"
        
        # Jika masih dalam periode cooldown, cek apakah sudah melebihi limit
        if user_data['count'] >= self.MAX_REQUESTS:
            time_left = user_data['reset_time'] - current_time
            hours_left = time_left.total_seconds() / 3600
            minutes_left = (time_left.total_seconds() % 3600) / 60
            
            if hours_left >= 1:
                time_str = f"{int(hours_left)} jam {int(minutes_left)} menit"
            else:
                time_str = f"{int(minutes_left)} menit"
            
            return False, f"⏳ Limit harian tercapai! Tunggu {time_str} lagi. Ingin akses tanpa batas? Ketik /id dan berikan id pada admin agar bisa akses bot"
        
        # Masih bisa request, tambah counter
        user_data['count'] += 1
        remaining_requests = self.MAX_REQUESTS - user_data['count']
        
        if remaining_requests > 0:
            return True, f"✅ Request berhasil! Sisa quota: {remaining_requests}/{self.MAX_REQUESTS}"
        else:
            return True, f"✅ Request berhasil! Quota habis, reset dalam {self.COOLDOWN_HOURS} jam."

    def get_user_status(self, user_id: int) -> str:
        """Get status lengkap untuk user tertentu"""
        if self.is_vip(user_id):
            return "👑 Status VIP: Unlimited requests"
            
        self._cleanup_expired_entries()
        
        if user_id not in self.user_limits:
            return f"📊 Status: {self.MAX_REQUESTS}/{self.MAX_REQUESTS} request tersisa"
        
        user_data = self.user_limits[user_id]
        current_time = datetime.now()
        
        if current_time >= user_data['reset_time']:
            return f"📊 Status: {self.MAX_REQUESTS}/{self.MAX_REQUESTS} request tersisa (reset)"
        
        remaining = self.MAX_REQUESTS - user_data['count']
        time_left = user_data['reset_time'] - current_time
        hours_left = time_left.total_seconds() / 3600
        minutes_left = (time_left.total_seconds() % 3600) / 60
        
        if hours_left >= 1:
            time_str = f"{int(hours_left)} jam {int(minutes_left)} menit"
        else:
            time_str = f"{int(minutes_left)} menit"
        
        return f"📊 Status: {remaining}/{self.MAX_REQUESTS} request tersisa, reset dalam {time_str}"

# Instance global rate limiter
rate_limiter = RateLimiter()

def with_rate_limit(func):
    """
    Decorator untuk menerapkan rate limiting pada function
    """
    @wraps(func)
    async def wrapper(update, context):
        user_id = update.effective_user.id
        
        # Cek rate limit
        is_allowed, message = rate_limiter.check_rate_limit(user_id)
        
        if not is_allowed:
            await update.message.reply_text(f"🚫 {message}")
            return
        
        # Jika allowed, jalankan function
        try:
            result = await func(update, context)
            return result
        except Exception as e:
            # Jika ada error, kembalikan quota (rollback) - kecuali untuk VIP
            if not rate_limiter.is_vip(user_id) and user_id in rate_limiter.user_limits:
                rate_limiter.user_limits[user_id]['count'] -= 1
                if rate_limiter.user_limits[user_id]['count'] <= 0:
                    del rate_limiter.user_limits[user_id]
            raise e
    
    return wrapper

# Command untuk cek status rate limit
async def cmd_quota_status(update, context):
    """Command untuk mengecek status quota user"""
    user_id = update.effective_user.id
    status_msg = rate_limiter.get_user_status(user_id)
    await update.message.reply_text(status_msg)