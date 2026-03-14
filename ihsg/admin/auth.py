import json
import os

USER_ROLE_PATH = "/home/ec2-user/package/admin/user_roles.json"
USER_ROLES = {}  # Format: {user_id: ["whitelist", "vip"]}

AUTHORIZED_ADMINS = {
    "superman": "kuncirahem",
}

def load_roles():
    global USER_ROLES
    if os.path.exists(USER_ROLE_PATH):
        with open(USER_ROLE_PATH, "r") as f:
            USER_ROLES = json.load(f)
            # Pastikan keys jadi int
            USER_ROLES = {int(k): v for k, v in USER_ROLES.items()}
    else:
        USER_ROLES = {}

def save_roles():
    with open(USER_ROLE_PATH, "w") as f:
        json.dump(USER_ROLES, f)

def check_admin_credentials(username, password):
    return AUTHORIZED_ADMINS.get(username) == password

def add_user(user_id, role):
    if user_id not in USER_ROLES:
        USER_ROLES[user_id] = []
    if role not in USER_ROLES[user_id]:
        USER_ROLES[user_id].append(role)
    save_roles()

def remove_user(user_id):
    if user_id in USER_ROLES:
        del USER_ROLES[user_id]
        save_roles()

def promote_user(user_id):
    if user_id in USER_ROLES and "vip" not in USER_ROLES[user_id]:
        USER_ROLES[user_id].append("vip")
        save_roles()

def is_authorized_user(user_id):
    return "whitelist" in USER_ROLES.get(user_id, [])

def is_vip_user(user_id):
    return "vip" in USER_ROLES.get(user_id, [])

def list_users():
    return USER_ROLES
