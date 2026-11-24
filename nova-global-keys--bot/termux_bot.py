import os, requests, telebot, sqlite3, uuid, secrets, time
from telebot import apihelper

print("🤖 [1] Bot script starting...", flush=True)

# ==========================================
# ⚠️ CONFIGURATION - UPDATE THESE 2 LINES ⚠️
# ==========================================
VPS_IP = "YOUR_VPS_PUBLIC_IP_HERE"  # <-- REPLACE WITH YOUR VPS IP
TOKEN = os.getenv("TELEGRAM_TOKEN") # Make sure to export this in Termux!
# ==========================================

# 1. Setup Cloudflare Worker Proxy (Bypasses ISP Blocks)
WORKER_URL = "https://my-first-worker.novaglobalkeys.workers.dev"
apihelper.API_URL = f"{WORKER_URL}/bot{{0}}/{{1}}"
apihelper.FILE_URL = f"{WORKER_URL}/file/bot{{0}}/{{1}}"
apihelper.CONNECT_TIMEOUT = 15
apihelper.READ_TIMEOUT = 15

bot = telebot.TeleBot(TOKEN)

# 2. Setup Local SQLite DB (No compilation needed!)
def init_db():
    conn = sqlite3.connect('nova_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (chat_id TEXT PRIMARY KEY, jwt TEXT, org_id INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def save_user(chat_id, jwt, org_id=1):
    conn = sqlite3.connect('nova_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (chat_id, jwt, org_id) VALUES (?, ?, ?)", (chat_id, jwt, org_id))
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect('nova_bot.db')
    c = conn.cursor()
    c.execute("SELECT jwt FROM users WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# API Endpoints
API_SMART = f"http://{VPS_IP}:8000/api/v1"
API_TOKEN = f"http://{VPS_IP}:8100/api/v1"

print("🤖 [2] Database ready. Starting commands...", flush=True)

# 3. Bot Commands
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    username = f"user_{chat_id}"
    password = uuid.uuid4().hex

    try:
        # Register user on the VPS
        res = requests.post(f"{API_SMART}/auth/register", json={
            "username": username, "password": password, "telegram_chat_id": chat_id
        }, timeout=10)
        
        # Login to get JWT
        login_res = requests.post(f"{API_SMART}/auth/token", data={
            "username": username, "password": password
        }, timeout=10)
        
        if login_res.status_code == 200:
            jwt = login_res.json()["access_token"]
            save_user(chat_id, jwt)
            bot.reply_to(message, f"🚀 <b>Welcome to Nova Protocol</b>\n\nID: <code>{chat_id}</code>\n\n<b>Commands:</b>\n/watch 0xAddress 10000\n/webhook https://your-url.com\n/dvp", parse_mode="HTML")
        else:
            bot.reply_to(message, "Registration failed.")
    except Exception as e:
        bot.reply_to(message, f"Error connecting to VPS: {e}")

@bot.message_handler(commands=['watch'])
def add_watch(message):
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Usage: <code>/watch 0xAddress 10000</code>", parse_mode="HTML")

    chat_id = str(message.chat.id)
    jwt = get_user(chat_id)
    if not jwt: return bot.reply_to(message, "Send /start first.")

    contract, amount = args[1], args[2]
    
    try:
        res = requests.post(f"{API_SMART}/watch", 
            headers={"Authorization": f"Bearer {jwt}"},
            json={"chain": "base", "contract_address": contract, "min_amount_usd": float(amount)},
            timeout=10
        )
        if res.status_code == 200:
            bot.reply_to(message, f"✅ Tracking:\n<code>{contract}</code>", parse_mode="HTML")
        else:
            bot.reply_to(message, f"Failed: {res.text}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['webhook'])
def add_webhook(message):
    args = message.text.split()
    if len(args) != 2:
        return bot.reply_to(message, "Usage: <code>/webhook https://webhook.site/...</code>", parse_mode="HTML")

    chat_id = str(message.chat.id)
    jwt = get_user(chat_id)
    if not jwt: return bot.reply_to(message, "Send /start first.")

    try:
        res = requests.post(f"{API_SMART}/client/webhooks", 
            headers={"Authorization": f"Bearer {jwt}"},
            json={"endpoint_url": args[1], "is_active": True},
            timeout=10
        )
        if res.status_code == 200:
            secret = res.json().get("secret_key", "Created")
            bot.reply_to(message, f"✅ <b>Webhook Registered!</b>\n\nURL: <code>{args[1]}</code>", parse_mode="HTML")
        else:
            bot.reply_to(message, f"Failed: {res.text}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['dvp'])
def trigger_dvp(message):
    chat_id = str(message.chat.id)
    msg = bot.reply_to(message, "🚀 Triggering live DvP Settlement on Base Mainnet...")
    
    try:
        # Hit the Tokenisation Core (Port 8100) to create an escrow
        res = requests.post(f"{API_TOKEN}/escrow/create", json={
            "investor_wallet": "0xA4eE963F223C193261d8545e4c4681ED3837af25",
            "asset_contract": "0x9991bE994829601F90328CCF9cee4D1A55ADae70",
            "currency_contract": "0x9991bE994829601F90328CCF9cee4D1A55ADae70",
            "share_amount": 100,
            "price_dkhyr": 5000
        }, timeout=10)
        
        if res.status_code == 200:
            bot.edit_message_text(f"✅ <b>DvP Escrow Created!</b>\n\nResponse:\n<code>{res.text}</code>", chat_id, msg.message_id, parse_mode="HTML")
        else:
            bot.edit_message_text(f"❌ Failed: {res.text}", chat_id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Network Error: {e}", chat_id, msg.message_id)

print("🤖 [3] Commands registered. Starting polling loop...", flush=True)

# 4. Crash-Proof Polling
if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"[!] Timeout or Error: {e}. Retrying in 3 seconds...", flush=True)
            time.sleep(3)
