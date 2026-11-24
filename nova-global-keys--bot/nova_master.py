import os
import json
import time
import shlex
import logging
from pathlib import Path
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("nova_master")

# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USE_WORKER = os.getenv("USE_WORKER", "true").strip().lower() in ("1", "true", "yes", "on")
WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "https://my-first-worker.novaglobalkeys.workers.dev").rstrip("/")
API_BASE = os.getenv("NOVA_API_BASE_URL", "http://127.0.0.1:8100/api/v1").rstrip("/")
HEALTH_URL = API_BASE.replace("/api/v1", "/health")

ADMIN_IDS = {int(x.strip()) for x in (os.getenv("ADMIN_TELEGRAM_IDS") or os.getenv("ADMIN_IDS") or "").split(",") if x.strip().isdigit()}
ASSET_CONTRACT = os.getenv("ASSET_CONTRACT", "0x11b229E0F4a0DAee8B8Bf20BdED941b7ba4E8C4c")
CURRENCY_CONTRACT = os.getenv("CURRENCY_CONTRACT", "0x9991bE994829601F90328CCF9cee4D1A55ADae70")
DEFAULT_PRICE_DKHYR = float(os.getenv("DEFAULT_SHARE_PRICE_DKHYR", "5000"))

# Wallet Linking File
WALLET_LINKS_FILE = Path(__file__).resolve().parent / "linked_wallets.json"

def _load_linked_wallets() -> dict:
    if WALLET_LINKS_FILE.exists():
        try: return json.loads(WALLET_LINKS_FILE.read_text())
        except Exception: return {}
    return {}

def _save_linked_wallets(data: dict) -> None:
    WALLET_LINKS_FILE.write_text(json.dumps(data, indent=2))

def resolve_wallet(user_id: int, args: list, arg_index: int = 0) -> str | None:
    if args and len(args) > arg_index and args[arg_index].strip().startswith("0x"):
        return args[arg_index].strip()
    return _load_linked_wallets().get(str(user_id))

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def api_request(method: str, endpoint: str, payload: dict = None):
    url = f"{API_BASE}{endpoint}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            if method == "GET":
                resp = await client.get(url, params=payload)
            else:
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json(), None
        except httpx.HTTPStatusError as e:
            return None, f"API Error {e.response.status_code}: {e.response.text}"
        except Exception as e:
            return None, f"Connection Error: {str(e)}"

# ==========================================
# 1. SYSTEM & WALLET CONNECT
# ==========================================
async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram ID: <code>{update.effective_user.id}</code>", parse_mode="HTML")

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        saved = _load_linked_wallets().get(user_id)
        if saved:
            return await update.message.reply_text(f"🔗 <b>Connected Wallet:</b> <code>{saved}</code>\nTo change: <code>/connect 0xNewWallet</code>", parse_mode="HTML")
        return await update.message.reply_text("Usage: <code>/connect 0xYourWalletAddress</code>", parse_mode="HTML")
    
    wallet = context.args[0].strip()
    if not wallet.startswith("0x") or len(wallet) != 42:
        return await update.message.reply_text("❌ Invalid EVM wallet address.")
    
    links = _load_linked_wallets()
    links[user_id] = wallet
    _save_linked_wallets(links)
    await update.message.reply_text(f"✅ <b>Wallet Connected!</b>\nAddress: <code>{wallet}</code>\nYou can now use <code>/buy 1</code> and <code>/sell 1</code> without typing the address.", parse_mode="HTML")

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(HEALTH_URL)
            await update.message.reply_text(f"✅ <b>API Online:</b> <code>{json.dumps(res.json())}</code>", parse_mode="HTML")
        except Exception:
            await update.message.reply_text("❌ API Offline (Is uvicorn running?)")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    menu = (
        "🌐 <b>Nova Global RWA Settlement Portal (v0.3.0)</b>\n\n"
        "<b>1. Identity &amp; Compliance:</b>\n"
        "• /connect 0xWallet — Link your wallet\n"
        "• /investor email \"Full Name\" Country — Register profile\n"
        "• /kycstatus [wallet] — Check whitelist status\n"
        "• /wallet [wallet] — Check DKHYR &amp; NVP-1 balances\n\n"
        "<b>2. Layer 3 DvP Escrow:</b>\n"
        "• /buy [wallet] &lt;shares&gt; — Create buy escrow\n"
        "• /sell [wallet] &lt;shares&gt; — Create sell escrow\n"
        "• /fund &lt;order_id&gt; &lt;0xTxHash&gt; — Fund escrow order\n"
        "• /settle &lt;order_id&gt; — Trigger atomic settlement\n"
        "• /orders — View active escrow orders\n\n"
        "<b>3. Portfolio &amp; Reporting:</b>\n"
        "• /statement [wallet] — Regulatory audit statement\n"
        "• /health — Check Core API status\n"
    )
    if is_admin(user_id):
        menu += "\n🔐 <b>Admin Controls:</b>\n• /whitelist &lt;wallet&gt; [Country]\n• /issue &lt;investor_id&gt; &lt;property_id&gt; &lt;shares&gt;"
    await update.message.reply_text(menu, parse_mode="HTML")

# ==========================================
# 2. IDENTITY & COMPLIANCE
# ==========================================
async def investor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: args = shlex.split(update.message.text)
    except Exception: return await update.message.reply_text("❌ Error parsing quotes.")
    if len(args) != 4:
        return await update.message.reply_text('Usage: <code>/investor test@nova.eu "Rizwan Ali" UK</code>', parse_mode="HTML")
    
    email, full_name, country = args[1].strip(), args[2].strip(), args[3].strip()[:2].upper()
    data, err = await api_request("POST", "/identity/investors", {"email": email, "full_name": full_name, "country": country})
    if err: await update.message.reply_text(f"❌ Error:\n<code>{err}</code>", parse_mode="HTML")
    else: await update.message.reply_text(f"✅ <b>Investor Created!</b>\nID: <code>{data.get('id')}</code>", parse_mode="HTML")

async def whitelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text(f"⛔ Access Denied. Your ID: <code>{update.effective_user.id}</code>", parse_mode="HTML")
    
    wallet = resolve_wallet(update.effective_user.id, context.args, 0)
    if not wallet:
        return await update.message.reply_text("Usage: <code>/whitelist 0xWallet [UK]</code>", parse_mode="HTML")
    
    jurisdiction = context.args[1].strip()[:2].upper() if len(context.args) > 1 else "UK"
    data, err = await api_request("POST", "/compliance/whitelist", {"wallet_address": wallet, "is_whitelisted": True, "jurisdiction": jurisdiction, "lockup_until": 0})
    if err: await update.message.reply_text(f"❌ Whitelist failed:\n<code>{err}</code>", parse_mode="HTML")
    else: await update.message.reply_text(f"✅ <b>Wallet Whitelisted!</b>\nAddress: <code>{wallet}</code>", parse_mode="HTML")

async def kycstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = resolve_wallet(update.effective_user.id, context.args, 0)
    if not wallet: return await update.message.reply_text("Usage: <code>/kycstatus 0xWallet</code>", parse_mode="HTML")
    data, err = await api_request("GET", f"/compliance/whitelist/{wallet}")
    if err: await update.message.reply_text(f"❌ Lookup failed:\n<code>{err}</code>", parse_mode="HTML")
    else:
        is_approved = bool(data.get("whitelisted") or data.get("is_whitelisted"))
        await update.message.reply_text(f"<b>Compliance Status</b>\nWallet: <code>{wallet}</code>\nResult: {'✅ Approved' if is_approved else '⏳ Pending'}", parse_mode="HTML")

# ==========================================
# 3. DVP ESCROW
# ==========================================
async def _create_escrow(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    if len(context.args) == 1:
        investor_wallet = resolve_wallet(update.effective_user.id, [], 0)
        if not investor_wallet: return await update.message.reply_text(f"Usage: <code>/{direction} 0xWallet shares</code> (or link via /connect)", parse_mode="HTML")
        amt_str = context.args[0].strip()
    elif len(context.args) >= 2:
        investor_wallet, amt_str = context.args[0].strip(), context.args[1].strip()
    else:
        return await update.message.reply_text(f"Usage: <code>/{direction} [0xWallet] shares</code>", parse_mode="HTML")

    try: share_amount = float(amt_str)
    except ValueError: return await update.message.reply_text("❌ Share amount must be a number.")

    payload = {"direction": direction, "investor_wallet": investor_wallet, "asset_contract": ASSET_CONTRACT, "currency_contract": CURRENCY_CONTRACT, "share_amount": share_amount, "price_dkhyr": DEFAULT_PRICE_DKHYR}
    data, err = await api_request("POST", "/escrow/create", payload)
    if err: return await update.message.reply_text(f"❌ Escrow failed:\n<code>{err}</code>", parse_mode="HTML")

    order_id = data.get("order_id") or data.get("id")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("1️⃣ Fund Escrow", callback_data=f"fund:{order_id}"), InlineKeyboardButton("2️⃣ Settle DvP", callback_data=f"settle:{order_id}")], [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel:{order_id}")]])
    await update.message.reply_text(f"🧾 <b>{direction.upper()} DvP Escrow Created</b>\nOrder ID: <code>{order_id}</code>\nShares: <code>{share_amount}</code>\n\nClick below to execute:", reply_markup=keyboard, parse_mode="HTML")

async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _create_escrow(update, context, "buy")

async def sell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _create_escrow(update, context, "sell")

async def fund_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await update.message.reply_text("Usage: <code>/fund order_id 0xTxHash</code>", parse_mode="HTML")
    order_id, tx_hash = context.args[0].strip(), context.args[1].strip()
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(f"{API_BASE}/escrow/{order_id}/fund", params={"deposit_tx_hash": tx_hash})
            resp.raise_for_status()
            await update.message.reply_text(f"✅ <b>Escrow FUNDED</b>\n<pre>{json.dumps(resp.json(), indent=2)}</pre>", parse_mode="HTML")
        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"❌ Fund failed ({e.response.status_code}):\n<code>{e.response.text}</code>", parse_mode="HTML")

async def settle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Usage: <code>/settle order_id</code>", parse_mode="HTML")
    await process_escrow_action(update.message, "settle", context.args[0].strip())

async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data, err = await api_request("GET", "/escrow/")
    if err: await update.message.reply_text(f"❌ Error:\n<code>{err}</code>", parse_mode="HTML")
    else: await update.message.reply_text(f"📋 <b>Escrow Orders</b>\n<pre>{json.dumps(data, indent=2)[:3500]}</pre>", parse_mode="HTML")

async def escrow_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, order_id = query.data.split(":", 1)
    if action == "fund":
        return await query.message.reply_text(f"💳 <b>Fund Escrow Order</b>\nSend deposit, then submit hash:\n\n<code>/fund {order_id} 0xTxHash</code>", parse_mode="HTML")
    await process_escrow_action(query.message, action, order_id)

async def process_escrow_action(message, action: str, order_id: str):
    data, err = await api_request("POST", f"/escrow/{order_id}/{action}", {})
    if err: await message.reply_text(f"❌ Failed to {action} order:\n<code>{err}</code>", parse_mode="HTML")
    else: await message.reply_text(f"✅ <b>Escrow {action.upper()} Complete</b>\n<pre>{json.dumps(data, indent=2)[:3500]}</pre>", parse_mode="HTML")

# ==========================================
# 4. REPORTING
# ==========================================
async def statement_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = resolve_wallet(update.effective_user.id, context.args, 0)
    if not wallet: return await update.message.reply_text("Usage: <code>/statement 0xWallet</code>", parse_mode="HTML")
    data, err = await api_request("GET", f"/reporting/investor/{wallet}/statement")
    if err: await update.message.reply_text(f"❌ Error:\n<code>{err}</code>", parse_mode="HTML")
    else: await update.message.reply_text(f"📑 <b>Investor Audit Statement</b>\n<pre>{json.dumps(data, indent=2)[:3500]}</pre>", parse_mode="HTML")

async def wallet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = resolve_wallet(update.effective_user.id, context.args, 0)
    if not wallet: return await update.message.reply_text("Usage: <code>/wallet 0xWallet</code>", parse_mode="HTML")
    await update.message.reply_text(f"🔗 Wallet: <code>{wallet}</code>\n(DKHYR/NVP-1 balance read logic goes here)", parse_mode="HTML")


async def settle_v2_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text(
            "Usage: <code>/settle_v2 order_id shares</code>\nExample: <code>/settle_v2 13d323c0... 1</code>", 
            parse_mode="HTML"
        )
    
    order_id = context.args[0].strip()
    try:
        share_amount = float(context.args[1].strip())
    except ValueError:
        return await update.message.reply_text("❌ Share amount must be a number.")
    
    seller = resolve_wallet(update.effective_user.id, [], 0)
    if not seller:
        return await update.message.reply_text("❌ No wallet connected. Use /connect 0xWallet first.")

    payload = {
        "order_id": order_id,
        "buyer": "0xA4eE963F223C193261d8545e4c4681ED3837af25", # Treasury acts as buyer in a SELL
        "seller": seller,
        "dkhyr_amount": share_amount * DEFAULT_PRICE_DKHYR,
        "share_amount": share_amount
    }
    
    data, err = await api_request("POST", "/settlement-v2/settle-atomic", payload)
    
    if err:
        await update.message.reply_text(f"❌ Atomic Settlement Failed:\n<code>{err}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"⚛️ <b>Atomic DvP Settled!</b>\n"
            f"Tx: <code>{data.get("tx_hash")}</code>\n"
            f"Settlement ID: <code>{data.get("settlement_id")}</code>",
            parse_mode="HTML"
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)) or "JSON" in str(err) or "525" in str(err):
        logger.warning("Transient Telegram/Cloudflare error. Retrying...")
        return
    logger.exception("Unhandled bot exception", exc_info=err)

# ==========================================
# ENTRYPOINT
# ==========================================
def build_app():
    builder = (ApplicationBuilder().token(BOT_TOKEN).connect_timeout(30.0).read_timeout(30.0).get_updates_read_timeout(35.0).get_updates_connect_timeout(30.0))
    if USE_WORKER and WORKER_URL: builder = builder.base_url(f"{WORKER_URL}/bot").base_file_url(f"{WORKER_URL}/file/bot")
    app = builder.build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler(["start", "menu"], start_cmd))
    app.add_handler(CommandHandler("whoami", whoami_cmd))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("investor", investor_cmd))
    app.add_handler(CommandHandler("whitelist", whitelist_cmd))
    app.add_handler(CommandHandler("kycstatus", kycstatus_cmd))
    app.add_handler(CommandHandler(["buy", "escrow"], buy_cmd))
    app.add_handler(CommandHandler("sell", sell_cmd))
    app.add_handler(CommandHandler("fund", fund_cmd))
    app.add_handler(CommandHandler("settle", settle_cmd))
    app.add_handler(CommandHandler("settle_v2", settle_v2_cmd))
    app.add_handler(CommandHandler("orders", orders_cmd))
    app.add_handler(CommandHandler("statement", statement_cmd))
    app.add_handler(CommandHandler("wallet", wallet_cmd))
    app.add_handler(CallbackQueryHandler(escrow_button_callback))
    return app

def main():
    logger.info("[2] Bot ready. Waiting for messages...")
    while True:
        try:
            app = build_app()
            app.run_polling(drop_pending_updates=True, bootstrap_retries=-1)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.warning("Polling loop interrupted (%s). Restarting in 5s...", e)
            time.sleep(5)

if __name__ == "__main__":
    main()
