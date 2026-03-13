from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from auth import check_admin_credentials, add_user, promote_user, remove_user, list_users
import asyncio

ASK_USERNAME, ASK_PASSWORD, ADMIN_MENU, BROADCAST_TARGET, BROADCAST_MESSAGE = range(5)

active_admins = set()

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡 Masukkan ID admin:")
    return ASK_USERNAME

async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['admin_username'] = update.message.text
    await update.message.reply_text("🔒 Masukkan password:")
    return ASK_PASSWORD

async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = context.user_data['admin_username']
    password = update.message.text

    if check_admin_credentials(username, password):
        active_admins.add(update.effective_user.id)
        await update.message.reply_text("""✅ Login berhasil.

📋 **MENU ADMIN:**

👥 **User Management:**
- `tambah <id> whitelist` - Tambah user whitelist
- `tambah <id> vip` - Tambah user VIP
- `naikkan <id>` - Promote user ke VIP
- `hapus <id>` - Hapus user
- `daftar` - Lihat daftar semua user

📢 **Broadcast:**
- `broadcast all` - Broadcast ke semua user VIP
- `broadcast <id>` - Broadcast ke user tertentu
- `broadcast vip` - Broadcast ke semua user VIP
- `broadcast whitelist` - Broadcast ke semua user whitelist""", parse_mode="Markdown")
        return ADMIN_MENU
    else:
        await update.message.reply_text("❌ ID atau Password salah.")
        return ConversationHandler.END
    

async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in active_admins:
        await update.message.reply_text("⛔ Kamu belum login sebagai admin.")
        return ConversationHandler.END

    text = update.message.text.lower().strip()
    parts = text.split()

    if text.startswith("tambah") and len(parts) == 3:
        try:
            user_id, role = int(parts[1]), parts[2]
            add_user(user_id, role)
            await update.message.reply_text(f"✅ User `{user_id}` ditambahkan sebagai `{role}`", parse_mode="Markdown")
        except:
            await update.message.reply_text("⚠️ Format salah. Gunakan: `tambah <id> whitelist/vip`", parse_mode="Markdown")

    elif text.startswith("naikkan") and len(parts) == 2:
        try:
            user_id = int(parts[1])
            promote_user(user_id)
            await update.message.reply_text(f"⬆️ User `{user_id}` dinaikkan menjadi VIP", parse_mode="Markdown")
        except:
            await update.message.reply_text("⚠️ Format salah. Gunakan: `naikkan <id>`", parse_mode="Markdown")

    elif text.startswith("hapus") and len(parts) == 2:
        try:
            user_id = int(parts[1])
            remove_user(user_id)
            await update.message.reply_text(f"🗑 User `{user_id}` dihapus dari daftar", parse_mode="Markdown")
        except:
            await update.message.reply_text("⚠️ Format salah. Gunakan: `hapus <id>`", parse_mode="Markdown")

    elif text.startswith("daftar"):
        data = list_users()
        if not data:
            await update.message.reply_text("📭 Tidak ada user terdaftar.")
        else:
            msg = "\n".join([f"{uid}: {', '.join(roles)}" for uid, roles in data.items()])
            await update.message.reply_text(f"📋 Daftar user:\n```\n{msg}\n```", parse_mode="Markdown")
            
    elif text.startswith("broadcast"):
        if len(parts) < 2:
            await update.message.reply_text("⚠️ Format: `broadcast all/vip/whitelist/<user_id>`", parse_mode="Markdown")
            return ADMIN_MENU
        
        target = parts[1]
        context.user_data['broadcast_target'] = target
        
        # Validasi target
        if target == "all":
            await update.message.reply_text("📢 Broadcast ke **SEMUA USER** (VIP + Whitelist)\n\n💬 Ketik pesan yang ingin dikirim:")
        elif target == "vip":
            await update.message.reply_text("📢 Broadcast ke **SEMUA USER VIP**\n\n💬 Ketik pesan yang ingin dikirim:")
        elif target == "whitelist":
            await update.message.reply_text("📢 Broadcast ke **SEMUA USER WHITELIST**\n\n💬 Ketik pesan yang ingin dikirim:")
        elif target.isdigit():
            user_id = int(target)
            data = list_users()
            if user_id in data:
                roles = ", ".join(data[user_id])
                await update.message.reply_text(f"📢 Broadcast ke **USER {user_id}** ({roles})\n\n💬 Ketik pesan yang ingin dikirim:")
            else:
                await update.message.reply_text("❌ User ID tidak ditemukan dalam database.")
                return ADMIN_MENU
        else:
            await update.message.reply_text("⚠️ Target tidak valid. Gunakan: `all`, `vip`, `whitelist`, atau `<user_id>`", parse_mode="Markdown")
            return ADMIN_MENU
        
        return BROADCAST_MESSAGE

    else:
        await update.message.reply_text("❓ Perintah tidak dikenal.")
    
    return ADMIN_MENU

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in active_admins:
        await update.message.reply_text("⛔ Kamu belum login sebagai admin.")
        return ConversationHandler.END

    target = context.user_data.get('broadcast_target')
    message = update.message.text
    
    if not target or not message:
        await update.message.reply_text("❌ Error dalam proses broadcast.")
        return ADMIN_MENU

    data = list_users()
    target_users = []
    
    # Tentukan target users berdasarkan parameter
    if target == "all":
        target_users = list(data.keys())
        target_desc = "SEMUA USER"
    elif target == "vip":
        target_users = [uid for uid, roles in data.items() if "vip" in roles]
        target_desc = "SEMUA USER VIP"
    elif target == "whitelist":
        target_users = [uid for uid, roles in data.items() if "whitelist" in roles and "vip" not in roles]
        target_desc = "SEMUA USER WHITELIST"
    elif target.isdigit():
        user_id = int(target)
        if user_id in data:
            target_users = [user_id]
            target_desc = f"USER {user_id}"
        else:
            await update.message.reply_text("❌ User ID tidak ditemukan.")
            return ADMIN_MENU
    
    if not target_users:
        await update.message.reply_text(f"📭 Tidak ada user untuk target: {target}")
        return ADMIN_MENU

    # Konfirmasi sebelum mengirim
    await update.message.reply_text(f"""📢 **KONFIRMASI BROADCAST**

🎯 **Target:** {target_desc}
👥 **Jumlah:** {len(target_users)} user
💬 **Pesan:**
{message}

✅ Ketik `ya` untuk mengirim
❌ Ketik `tidak` untuk batal""")
    
    context.user_data['broadcast_message'] = message
    context.user_data['target_users'] = target_users
    context.user_data['target_desc'] = target_desc
    return BROADCAST_TARGET

async def handle_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in active_admins:
        await update.message.reply_text("⛔ Kamu belum login sebagai admin.")
        return ConversationHandler.END

    response = update.message.text.lower().strip()
    
    if response == "ya":
        target_users = context.user_data.get('target_users', [])
        message = context.user_data.get('broadcast_message', '')
        target_desc = context.user_data.get('target_desc', '')
        
        # Format pesan broadcast
        broadcast_msg = f"""📢 **BROADCAST ADMIN**

{message}

---
_Pesan ini dikirim oleh admin_"""

        success_count = 0
        failed_count = 0
        
        status_msg = await update.message.reply_text("📤 Mengirim broadcast...")
        
        # Kirim pesan ke setiap user
        for user_id in target_users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=broadcast_msg,
                    parse_mode="Markdown"
                )
                success_count += 1
                await asyncio.sleep(0.1)  # Delay kecil untuk menghindari rate limit
            except Exception as e:
                failed_count += 1
                print(f"Failed to send to {user_id}: {e}")
        
        # Update status
        result_msg = f"""✅ **BROADCAST SELESAI**

🎯 Target: {target_desc}
✅ Berhasil: {success_count}
❌ Gagal: {failed_count}
📊 Total: {len(target_users)}"""

        await status_msg.edit_text(result_msg)
        
    elif response == "tidak":
        await update.message.reply_text("❌ Broadcast dibatalkan.")
    else:
        await update.message.reply_text("⚠️ Ketik `ya` untuk mengirim atau `tidak` untuk batal.")
        return BROADCAST_TARGET
    
    # Clear broadcast data
    context.user_data.pop('broadcast_target', None)
    context.user_data.pop('broadcast_message', None)
    context.user_data.pop('target_users', None)
    context.user_data.pop('target_desc', None)
    
    return ADMIN_MENU

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚪 Keluar dari mode admin.")
    return ConversationHandler.END

def get_admin_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_password)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login)],
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_command_handler)],
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message)],
            BROADCAST_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_confirmation)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)],
        allow_reentry=True
    )
