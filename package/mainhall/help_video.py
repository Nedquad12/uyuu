import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

async def helpvideo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /helpvideo - menampilkan pilihan video tutorial"""
    
    # Buat inline keyboard dengan pilihan video tutorial
    keyboard = [
        [InlineKeyboardButton("📊 DOM/Stock Tutorial", callback_data="video_domstock")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    help_text = """
🎥 **VIDEO TUTORIAL**

Pilih tutorial yang ingin Anda tonton:
    """
    
    await update.message.reply_text(
        help_text, 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def helpvideo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk callback dari pilihan video tutorial"""
    
    query = update.callback_query
    await query.answer()
    
    if query.data == "video_domstock":
        # Path ke file video tutorial DOM/Stock
        video_path = "/home/ec2-user/help/domstock"
        
        try:
            # Cek apakah file/folder exists
            if os.path.exists(video_path):
                # Jika path adalah folder, cari file video di dalamnya
                if os.path.isdir(video_path):
                    # Cari file video dalam folder (format video umum)
                    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
                    video_files = []
                    
                    for file in os.listdir(video_path):
                        if any(file.lower().endswith(ext) for ext in video_extensions):
                            video_files.append(os.path.join(video_path, file))
                    
                    if video_files:
                        # Ambil video pertama yang ditemukan
                        video_file = video_files[0]
                        
                        # Kirim video
                        with open(video_file, 'rb') as video:
                            await query.edit_message_text("📤 Sedang mengirim video tutorial...")
                            await context.bot.send_video(
                                chat_id=query.message.chat_id,
                                video=video,
                                caption="🎥 **Tutorial DOM/Stock Upload**\n\nVideo tutorial cara upload file DOM dan Stock",
                                parse_mode='Markdown'
                            )
                            
                        # Edit pesan untuk memberikan feedback
                        await query.edit_message_text(
                            "✅ Video tutorial DOM/Stock berhasil dikirim!",
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text(
                            "❌ Tidak ditemukan file video dalam folder tutorial.",
                            parse_mode='Markdown'
                        )
                
                # Jika path adalah file langsung
                elif os.path.isfile(video_path):
                    with open(video_path, 'rb') as video:
                        await query.edit_message_text("📤 Sedang mengirim video tutorial...")
                        await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=video,
                            caption="🎥 **Tutorial DOM/Stock Upload**\n\nVideo tutorial cara upload file DOM dan Stock",
                            parse_mode='Markdown'
                        )
                        
                    await query.edit_message_text(
                        "✅ Video tutorial DOM/Stock berhasil dikirim!",
                        parse_mode='Markdown'
                    )
            else:
                await query.edit_message_text(
                    "❌ File video tutorial tidak ditemukan.\n\nSilakan hubungi admin untuk memperbarui video tutorial.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            await query.edit_message_text(
                f"❌ Terjadi kesalahan saat mengirim video:\n`{str(e)}`",
                parse_mode='Markdown'
            )
    
    else:
        await query.edit_message_text(
            "❌ Pilihan tidak valid.",
            parse_mode='Markdown'
        )