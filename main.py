import asyncio
import sqlite3
import nest_asyncio
import requests
import os
import logging
import threading
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, Response

# Game imports (replace with your actual game modules)
from basketball import basketball_command, basketball_button_handler, basketball_text_handler
from bowling import bowling_command, bowling_button_handler, bowling_text_handler
from coin import coin_command, coin_button_handler
from darts import dart_command, dart_button_handler, dart_text_handler
from dice import dice_command, dice_button_handler, dice_text_handler
from football import football_command, football_button_handler, football_text_handler
from mines import mine_command, mine_button_handler
from predict import predict_command, predict_button_handler
from roulette import roulette_command, roulette_button_handler
from slots import slots_command, slots_button_handler
from tower import tower_command, tower_button_handler

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Allow nested event loops
nest_asyncio.apply()

# Bot configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8118951743:AAHT6bOYhmzl98fyKXvkfvez6refrn5dOlU")
NOWPAYMENTS_API_KEY = "86WDA8Y-A7V4Y5Y-N0ETC4V-JXB03GA"  # Verify this key is correct
WEBHOOK_URL = "https://casino-bot-41de.onrender.com"  # Ensure this matches your deployment

# Database functions
def init_db():
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_deposits 
                     (payment_id TEXT PRIMARY KEY, user_id INTEGER, currency TEXT)''')
        conn.commit()

def user_exists(user_id):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone() is not None

def get_user_balance(user_id):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        return result[0] if result else 0.0

def update_user_balance(user_id, new_balance):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        conn.commit()

def add_pending_deposit(payment_id, user_id, currency):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO pending_deposits (payment_id, user_id, currency) VALUES (?, ?, ?)",
                  (payment_id, user_id, currency))
        conn.commit()

def get_pending_deposit(payment_id):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, currency FROM pending_deposits WHERE payment_id = ?", (payment_id,))
        return c.fetchone()

def remove_pending_deposit(payment_id):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("DELETE FROM pending_deposits WHERE payment_id = ?", (payment_id,))
        conn.commit()

# Helper functions
def create_deposit_payment(user_id, currency='ltc'):
    try:
        url = "https://api.nowpayments.io/v1/payment"
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        payload = {
            "price_amount": 0,  # Allow any amount
            "price_currency": currency,
            "pay_currency": currency,
            "ipn_callback_url": f"{WEBHOOK_URL}/webhook",
            "order_id": f"deposit_{user_id}_{int(time.time())}",
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        if 'pay_address' not in data or 'payment_id' not in data:
            raise ValueError("Invalid response from NOWPayments")
        return data
    except Exception as e:
        logger.error(f"Deposit creation failed: {e}")
        raise

def create_payout(user_id, amount_usd, address):
    try:
        ltc_price = get_ltc_to_usd_price()
        amount_ltc = amount_usd / ltc_price
        url = "https://api.nowpayments.io/v1/payout"
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        payload = {
            "price_amount": amount_ltc,
            "price_currency": "ltc",
            "pay_currency": "ltc",
            "ipn_callback_url": f"{WEBHOOK_URL}/payout_webhook",
            "order_id": f"withdrawal_{user_id}_{int(time.time())}",
            "address": address
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Payout creation failed: {e}")
        return None

def get_ltc_to_usd_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data['litecoin']['usd']
    except Exception as e:
        logger.error(f"Failed to fetch LTC price: {e}")
        return 100.0  # Fallback price

def format_expiration_time(expiration_date_str):
    try:
        expiration_time = datetime.strptime(expiration_date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        now = datetime.utcnow()
        time_left = expiration_time - now
        minutes, seconds = divmod(int(time_left.total_seconds()), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:01d}:{minutes:02d}:{seconds:02d}"
    except:
        return "1:00:00"

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    if not user_exists(user_id):
        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 0.0)", (user_id, username))
            conn.commit()
    text = (
        "📣 How To Start?\n"
        "1. Make sure you have a balance. Use /balance to deposit.\n"
        "2. Join a group in @BalticGames directory.\n"
        "3. Try /dice to start playing!\n\n"
        "📣 Available Games:\n"
        "• 🎲 Dice - /dice\n"
        "• 🎳 Bowling - /bowl\n"
        "• 🎯 Darts - /dart\n"
        "• ⚽️ Football - /football\n"
        "• 🏀 Basketball - /basketball\n"
        "• 🪙 Coinflip - /coin\n"
        "• 🎰 Slots - /slots\n"
        "• 🎲 Predict - /predict\n"
        "• 💣 Mines - /mine\n"
        "• 🐒 Tower - /tower\n"
        "• 🎰 Roulette - /roul\n\n"
        "Have fun! 🍀"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def balance_command(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not user_exists(user_id):
        await context.bot.send_message(chat_id=chat_id, text="Please register with /start.")
        return
    balance = get_user_balance(user_id)
    text = f"Your balance: ${balance:.2f}"
    keyboard = [
        [InlineKeyboardButton("Deposit", callback_data="deposit"),
         InlineKeyboardButton("Withdraw", callback_data="withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

async def button_handler(update, context):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if data == "deposit":
        if update.effective_chat.type != 'private':
            await context.bot.send_message(chat_id=chat_id, text="Please start a private conversation with me to proceed with the deposit.")
        else:
            try:
                payment_data = create_deposit_payment(user_id, 'ltc')
                address = payment_data['pay_address']
                payment_id = payment_data['payment_id']
                expiration_time = payment_data.get('expiration_estimate_date', '')
                expires_in = format_expiration_time(expiration_time) if expiration_time else "1:00:00"
                add_pending_deposit(payment_id, user_id, 'ltc')
                text = (
                    "💳 Litecoin Deposit\n\n"
                    f"LTC address: `{address}`\n"
                    f"Expires in: {expires_in}\n"
                    "Send any amount of LTC to this address."
                )
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Deposit error: {e}")
                await context.bot.send_message(chat_id=chat_id, text="Failed to generate deposit address. Try again or contact support.")
        await query.answer()
    elif data == "withdraw":
        if update.effective_chat.type != 'private':
            await context.bot.send_message(chat_id=chat_id, text="Please start a private conversation with me to proceed with the withdrawal.")
        else:
            balance = get_user_balance(user_id)
            await context.bot.send_message(chat_id=chat_id, text=f"Your balance: ${balance:.2f}\nPlease enter amount and LTC address (e.g., '5.00 LTC123...')")
            context.user_data['expecting_withdrawal_details'] = True
        await query.answer()
    else:
        await query.answer("Unknown action.")

async def text_handler(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if context.user_data.get('expecting_withdrawal_details'):
        try:
            parts = update.message.text.strip().split()
            amount_usd = float(parts[0])
            address = " ".join(parts[1:])
            if not address.startswith("L"):
                raise ValueError("Invalid LTC address")
            balance = get_user_balance(user_id)
            if amount_usd <= 0:
                raise ValueError("Amount must be positive")
            if amount_usd > balance:
                await context.bot.send_message(chat_id=chat_id, text="Insufficient balance.")
                return
            payout_data = create_payout(user_id, amount_usd, address)
            if payout_data:
                new_balance = balance - amount_usd
                update_user_balance(user_id, new_balance)
                await context.bot.send_message(chat_id=chat_id, text=f"Withdrawal of ${amount_usd:.2f} to `{address}` initiated. New balance: ${new_balance:.2f}", parse_mode='Markdown')
            else:
                await context.bot.send_message(chat_id=chat_id, text="Withdrawal failed. Check your address or try again.")
        except ValueError as e:
            await context.bot.send_message(chat_id=chat_id, text=f"Invalid input: {str(e)}. Please enter 'amount address', e.g., '5.00 LTC123...'")
        except Exception as e:
            logger.error(f"Withdrawal error: {e}")
            await context.bot.send_message(chat_id=chat_id, text="An error occurred. Please try again.")
        finally:
            context.user_data['expecting_withdrawal_details'] = False
    else:
        await context.bot.send_message(chat_id=chat_id, text="I don’t understand that command.")

async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Unhandled update: {update}")

# Flask app for webhooks
app = Flask(__name__)

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return Response(status=200)

@app.route('/webhook', methods=['POST'])
def nowpayments_webhook():
    data = request.json
    logger.info(f"NOWPayments Webhook: {data}")
    if data.get('payment_status') == 'finished':
        payment_id = data['payment_id']
        pay_amount = float(data.get('pay_amount', 0))
        if pay_amount > 0:
            deposit = get_pending_deposit(payment_id)
            if deposit:
                user_id, currency = deposit
                if currency == 'ltc':
                    try:
                        ltc_price = get_ltc_to_usd_price()
                        usd_amount = pay_amount * ltc_price
                        current_balance = get_user_balance(user_id)
                        new_balance = current_balance + usd_amount
                        update_user_balance(user_id, new_balance)
                        remove_pending_deposit(payment_id)
                        asyncio.run_coroutine_threadsafe(
                            app.bot.send_message(
                                chat_id=user_id,
                                text=f"✅ Deposit of {pay_amount} LTC (${usd_amount:.2f}) confirmed! New balance: ${new_balance:.2f}"
                            ),
                            loop
                        )
                    except Exception as e:
                        logger.error(f"Webhook processing error: {e}")
    return Response(status=200)

@app.route('/payout_webhook', methods=['POST'])
def payout_webhook():
    data = request.json
    logger.info(f"Payout Webhook: {data}")
    if data.get('payout_status') == 'finished':
        order_id = data['order_id']
        user_id = int(order_id.split('_')[1])
        asyncio.run_coroutine_threadsafe(
            app.bot.send_message(chat_id=user_id, text="✅ Your withdrawal has been confirmed!"),
            loop
        )
    return Response(status=200)

def run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

async def main():
    global application, loop
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    await application.initialize()
    app.bot = application.bot

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_handler(CommandHandler("basketball", basketball_command))
    application.add_handler(CommandHandler("bowl", bowling_command))
    application.add_handler(CommandHandler("coin", coin_command))
    application.add_handler(CommandHandler("dart", dart_command))
    application.add_handler(CommandHandler("dice", dice_command))
    application.add_handler(CommandHandler("football", football_command))
    application.add_handler(CommandHandler("mine", mine_command))
    application.add_handler(CommandHandler("predict", predict_command))
    application.add_handler(CommandHandler("roul", roulette_command))
    application.add_handler(CommandHandler("slots", slots_command))
    application.add_handler(CommandHandler("tower", tower_command))
    application.add_handler(CallbackQueryHandler(basketball_button_handler, pattern="^basketball_"))
    application.add_handler(CallbackQueryHandler(bowling_button_handler, pattern="^bowl_"))
    application.add_handler(CallbackQueryHandler(coin_button_handler, pattern="^coin_"))
    application.add_handler(CallbackQueryHandler(dart_button_handler, pattern="^(dart_|accept_|cancel_)"))
    application.add_handler(CallbackQueryHandler(dice_button_handler, pattern="^dice_"))
    application.add_handler(CallbackQueryHandler(football_button_handler, pattern="^football_"))
    application.add_handler(CallbackQueryHandler(mine_button_handler, pattern="^mine_"))
    application.add_handler(CallbackQueryHandler(predict_button_handler, pattern="^predict_"))
    application.add_handler(CallbackQueryHandler(roulette_button_handler, pattern="^roul_"))
    application.add_handler(CallbackQueryHandler(slots_button_handler, pattern="^slots_"))
    application.add_handler(CallbackQueryHandler(tower_button_handler, pattern="^tower_"))
    application.add_handler(MessageHandler(filters.ALL, fallback_handler))

    loop = asyncio.new_event_loop()
    threading.Thread(target=run_loop, args=(loop,), daemon=True).start()
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram-webhook")
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask app on port {port}...")
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    asyncio.run(main())
