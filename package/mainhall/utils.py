import sys
sys.path.append ("/home/ec2-user/package/admin")
from functools import wraps
from auth import is_authorized_user as check_user_role

def is_authorized_user(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        uid = update.effective_user.id
        chat_type = update.effective_chat.type
        
        if chat_type == 'private' and not check_user_role(uid):
            await update.message.reply_text("⚠️ Anda tidak memiliki akses ke fitur ini. Hubungi @Rendanggedang untuk izin akses.")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper
