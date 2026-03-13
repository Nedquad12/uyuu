import sys
sys.path.append ("/home/ec2-user/package/admin")
from collections import defaultdict, deque
from functools import wraps
import time
from telegram import Update
from telegram.ext import ContextTypes
import pandas as pd
from collections import defaultdict
from datetime import datetime
import os
from auth import is_vip_user

REQUEST_COOLDOWN = 10
request_queue = deque()
user_last_request = defaultdict(float)
user_busy_flags = defaultdict(bool)

USER_TRACKING_FILE = "/home/ec2-user/package/user_tracking.xlsx"

def save_user_activity(user_id, username, first_name, last_name, user_input, timestamp):
    """
    Menyimpan aktivitas user ke file Excel
    """
    try:
        # Data user yang akan disimpan
        user_data = {
            'user_id': user_id,
            'username': username or '',
            'first_name': first_name or '',
            'last_name': last_name or '',
            'full_name': f"{first_name or ''} {last_name or ''}".strip(),
            'input': user_input[:500] if user_input else '',  # Batasi panjang input
            'timestamp': timestamp,
            'date': timestamp.strftime('%Y-%m-%d'),
            'time': timestamp.strftime('%H:%M:%S')
        }
        
        # Cek apakah file sudah ada
        if os.path.exists(USER_TRACKING_FILE):
            # Baca data yang sudah ada
            try:
                df_existing = pd.read_excel(USER_TRACKING_FILE)
                # Tambah data baru
                df_new = pd.DataFrame([user_data])
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            except Exception as e:
                print(f"Error reading existing file: {e}")
                # Jika error, buat dataframe baru
                df_combined = pd.DataFrame([user_data])
        else:
            # Buat dataframe baru jika file belum ada
            df_combined = pd.DataFrame([user_data])
        
        # Simpan ke file Excel
        df_combined.to_excel(USER_TRACKING_FILE, index=False)
        
    except Exception as e:
        print(f"Error saving user activity: {e}")

def spy(handler_func):
    """
    Decorator untuk melacak aktivitas user
    Menyimpan user_id, username, input, dan waktu terakhir menggunakan bot
    """
    @wraps(handler_func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            user = update.effective_user
            user_id = user.id
            username = user.username
            first_name = user.first_name
            last_name = user.last_name
            
            # Ambil input user (text message)
            user_input = ""
            if update.message and update.message.text:
                user_input = update.message.text
            elif update.callback_query and update.callback_query.data:
                user_input = f"callback: {update.callback_query.data}"
            
            # Timestamp saat ini
            timestamp = datetime.now()
            
            # Simpan aktivitas user
            save_user_activity(user_id, username, first_name, last_name, user_input, timestamp)
            
        except Exception as e:
            print(f"Error in spy decorator: {e}")
        
        # Jalankan fungsi asli
        return await handler_func(update, context, *args, **kwargs)
    
    return wrapper

def with_queue_control(handler_func):
    @wraps(handler_func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        current_time = time.time()

        is_vip = is_vip_user(user_id)  # ✅ pakai auth.py
        cooldown = 1 if is_vip else REQUEST_COOLDOWN

        if not is_vip and user_busy_flags[user_id]:
            await update.message.reply_text("⏳ Proses sebelumnya masih berjalan.")
            return

        if current_time - user_last_request[user_id] < cooldown:
            remaining = cooldown - (current_time - user_last_request[user_id])
            await update.message.reply_text(f"❗ Tunggu {remaining:.1f} detik sebelum request berikutnya. Ingin akses sepuasnya? Ketik /id dan berikan id pada admin agar bisa akses bot")
            return

        if not is_vip:
            request_queue.append(user_id)
            queue_position = list(request_queue).index(user_id) + 1
            if queue_position > 1:
                await update.message.reply_text(
                    f"⏳ Anda berada di antrian ke [{queue_position}]. Harap tunggu..."
                )
                request_queue.remove(user_id)
                return
            user_busy_flags[user_id] = True

        user_last_request[user_id] = current_time

        try:
            return await handler_func(update, context, *args, **kwargs)
        except Exception as e:
            await update.message.reply_text(f"❌ Terjadi kesalahan: {e}")
        finally:
            if not is_vip:
                if user_id in request_queue:
                    request_queue.remove(user_id)
                user_busy_flags[user_id] = False

    return wrapper

def vip(handler_func):
    """
    Decorator untuk membatasi akses fitur khusus VIP
    Hanya user yang ada di list VIP yang bisa mengakses fitur ini
    """
    @wraps(handler_func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "User"
        
        # Cek apakah user adalah VIP
        if not is_vip_user(user_id):
            await update.message.reply_text(
                f"🚫 Maaf {user_name}, anda belum memberikan id .\n"
                f"💎 Ketik /id dan berikan id pada admin agar bisa akses bot"
            )
            return
        
        # Jika VIP, jalankan fungsi asli
        try:
            return await handler_func(update, context, *args, **kwargs)
        except Exception as e:
            await update.message.reply_text(f"❌ Terjadi kesalahan: {e}")
    
    return wrapper