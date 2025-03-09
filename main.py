import asyncio
import sqlite3
import nest_asyncio
import requests
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from flask import Flask, request, Response

# Import game-specific handlers
from basketball.basketball import basketball_command, basketball_button_handler, basketball_text_handler
from bowling.bowling import bowling_command, bowling_button_handler, bowling_text_handler
from coin.coin import coin_command, coin_button_handler
from darts.darts import dart_command, dart_button_handler, dart_text_handler
from dice.dice import dice_command, dice_button_handler, dice_text_handler
from football.football import football_command, football_button_handler, football_text_handler
from mines.mines import mine_command, mine_button_handler
from predict.predict import predict_command, predict_button_handler
from roulette.roul import roulette_command, roulette_button_handler
from slots.slots import slots_command, slots_button_handler
from tower.tower import tower_command, tower_button_handler

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Bot configuration using environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8118951743:AAHT6bOYhmzl98fyKXvkfvez6refrn5dOlU")
NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "86WDA8Y-A7V4Y5Y-N0ETC4V-JXB03GA")

# Database functions (from database.py)
def init_db():
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_deposits 
                     (payment_id TEXT PRIMARY KEY, user_id INTEGER, amount REAL, currency TEXT)''')
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

def add_pending_deposit(payment_id, user_id, amount, currency):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("INSERT INTO pending_deposits (payment_id, user_id, amount, currency) VALUES (?, ?, ?, ?)",
                  (payment_id, user_id, amount, currency))
        conn.commit()

def get_pending_deposit(payment_id):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount FROM pending_deposits WHERE payment_id = ?", (payment_id,))
        return c.fetchone()

def remove_pending_deposit(payment_id):
    with sqlite3.connect('users.db') as conn:
        c = conn.cursor()
        c.execute("DELETE FROM pending_deposits WHERE payment_id = ?", (payment_id,))
        conn.commit()

# Fetch USDT to LTC exchange rate from CoinGecko
def get_usdt_to_ltc_rate():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=ltc")
        rate = response.json()["tether"]["ltc"]
        return rate
    except Exception:
        return 1.0  # Fallback rate if API fails

# Fetch minimal deposit amount from NOWPayments
def get_min_deposit_amount(crypto):
    try:
        url = f"https://api.nowpayments.io/v1/min-amount?currency_from={crypto}"
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return float(data["min_amount"])
    except Exception as e:
        print(f"Failed to fetch min amount for {crypto}: {e}")
        return 0.01  # Fallback minimal amount

# Command handlers
async def start_command(update, context):
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
        "2. Go to one of our groups in @BalticGames directory.\n"
        "3. Enter a game command (e.g., /dice) and play!\n\n"
        "📣 Available Games:\n"
        "• 🎲 Dice - /dice\n"
        "• 🎳 Bowling - /bowl\n"
        "• 🎯 Darts - /dart\n"
        "• ⚽️ Football - /football\n"
        "• 🏀 Basketball - /basketball\n"
        "• 🪙 Coinflip - /coin\n"
        "• 🎰 Slot Machine - /slots\n"
        "• 🎲 Dice Prediction - /predict\n"
        "• 💣 Mines - /mine\n"
        "• 🐒 Monkey Tower - /tower\n"
        "• 🎰 Roulette - /roul\n\n"
        "Enjoy the games! 🍀"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def balance_command(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not user_exists(user_id):
        await context.bot.send_message(chat_id=chat_id, text="Please register with /start.")
        return

    balance_usdt = get_user_balance(user_id)
    rate_usdt_to_ltc = get_usdt_to_ltc_rate()
    balance_ltc = balance_usdt * rate_usdt_to_ltc

    text = f"Your balance: ${balance_usdt:.2f} USDT ({balance_ltc:.6f} LTC)"
    keyboard = [
        [InlineKeyboardButton("Deposit", callback_data="deposit"),
         InlineKeyboardButton("Withdraw", callback_data="withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

# Button handlers for deposit/withdraw
async def check_private_chat(update, context):
    query = update.callback_query
    chat_type = query.message.chat.type
    bot_username = "diceLive_bot"  # Replace with your bot's username if different

    if chat_type != 'private':
        text = f"💬 These options are only available through the bot. Click here to proceed: https://t.me/{bot_username}"
        await context.bot.send_message(chat_id=query.message.chat_id, text=text)
        await query.answer()
        return False
    return True

async def deposit_handler(update, context):
    if not await check_private_chat(update, context):
        return

    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    text = "💳 Deposit\n\nChoose your preferred deposit method:"
    keyboard = [
        [InlineKeyboardButton("SOLANA", callback_data="deposit_sol"),
         InlineKeyboardButton("BTC", callback_data="deposit_btc"),
         InlineKeyboardButton("LTC", callback_data="deposit_ltc")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
    await query.answer()

async def generate_deposit_address(update, context, crypto):
    query = update.callback_query
    user_id = update.effective_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    currency_map = {
        "sol": {"name": "Solana", "symbol": "SOL"},
        "btc": {"name": "Bitcoin", "symbol": "BTC"},
        "ltc": {"name": "Litecoin", "symbol": "LTC"}
    }
    currency_info = currency_map.get(crypto)
    if not currency_info:
        await context.bot.edit_message_text("Invalid selection.", chat_id=chat_id, message_id=message_id)
        return

    min_amount = get_min_deposit_amount(crypto)

    try:
        payload = {
            "price_amount": min_amount,
            "price_currency": crypto,
            "pay_currency": crypto,
            "order_id": f"{user_id}_{int(query.message.date.timestamp())}",
            "order_description": "Deposit to bot balance",
            "ipn_callback_url": "https://casino-bot.onrender.com/webhook"  # Update after deployment
        }
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        response = requests.post("https://api.nowpayments.io/v1/payment", json=payload, headers=headers)
        response.raise_for_status()
        payment_data = response.json()
        if "pay_address" not in payment_data or "payment_id" not in payment_data:
            raise KeyError("Required fields missing in response")
        address = payment_data["pay_address"]
        payment_id = payment_data["payment_id"]

        add_pending_deposit(payment_id, user_id, min_amount, crypto)

        text = (
            f"💳 {currency_info['name']} deposit\n\n"
            f"Send at least {min_amount} {currency_info['symbol']} to this address:\n"
            f"{address}\n\n"
            "Note: This address is valid for 1 hour. You’ll be notified when the deposit is confirmed."
        )
        await context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Failed to create deposit payment for {crypto}: {e}")
        print(f"API Response: {response.text if 'response' in locals() else 'No response'}")
        await context.bot.edit_message_text("Failed to generate deposit address. Try again later.", chat_id=chat_id, message_id=message_id)
    await query.answer()

async def withdraw_handler(update, context):
    if not await check_private_chat(update, context):
        return

    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    text = "💸 Withdraw\n\nEnter the amount in USD and your LTC address, e.g., '5.00 LTC123...'."
    await context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
    context.user_data['expecting_withdrawal_details'] = True
    await query.answer()

async def button_handler(update, context):
    query = update.callback_query
    data = query.data
    if data == "deposit":
        await deposit_handler(update, context)
    elif data.startswith("deposit_"):
        crypto = data.split("_")[1]
        await generate_deposit_address(update, context, crypto)
    elif data == "withdraw":
        await withdraw_handler(update, context)

async def text_handler(update, context):
    if context.user_data.get('expecting_withdrawal_details'):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        text = update.message.text.strip().split()
        
        if len(text) < 2:
            await context.bot.send_message(chat_id=chat_id, text="Please provide amount and LTC address, e.g., '5.00 LTC123...'")
            return
        
        try:
            amount_usd = float(text[0])
            withdrawal_address = text[1]
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Invalid amount. Use a number, e.g., '5.00 LTC123...'")
            return

        balance = get_user_balance(user_id)
        if amount_usd <= 0:
            await context.bot.send_message(chat_id=chat_id, text="Amount must be greater than zero.")
            context.user_data['expecting_withdrawal_details'] = False
            return
        if amount_usd > balance:
            await context.bot.send_message(chat_id=chat_id, text="Insufficient balance.")
            context.user_data['expecting_withdrawal_details'] = False
            return

        rate_usdt_to_ltc = get_usdt_to_ltc_rate()
        amount_ltc = amount_usd * rate_usdt_to_ltc

        try:
            url = "https://api.nowpayments.io/v1/payout"
            headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}
            payload = {
                "currency": "ltc",
                "amount": amount_ltc,
                "address": withdrawal_address,
                "order_id": f"withdrawal_{user_id}_{int(asyncio.get_event_loop().time())}"
            }
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            new_balance = balance - amount_usd
            update_user_balance(user_id, new_balance)
            await context.bot.send_message(chat_id=chat_id, text=f"💸 Withdrawn ${amount_usd:.2f} ({amount_ltc:.6f} LTC) to {withdrawal_address}. New balance: ${new_balance:.2f}")
        except Exception as e:
            print(f"Failed to process withdrawal: {e}")
            print(f"API Response: {response.text if 'response' in locals() else 'No response'}")
            await context.bot.send_message(chat_id=chat_id, text="Failed to process withdrawal. Try again later.")
        
        context.user_data['expecting_withdrawal_details'] = False

# Flask app for webhook
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"Webhook received: {data}")  # For debugging
    if data.get('payment_status') == 'finished':
        payment_id = data['payment_id']
        deposit = get_pending_deposit(payment_id)
        if deposit:
            user_id, amount = deposit
            current_balance = get_user_balance(user_id)
            new_balance = current_balance + amount  # Amount in crypto units for now
            update_user_balance(user_id, new_balance)
            remove_pending_deposit(payment_id)
            asyncio.run_coroutine_threadsafe(
                app.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Deposit of {amount} {data['pay_currency'].upper()} confirmed! New balance: ${new_balance:.2f}"
                ),
                asyncio.get_event_loop()
            )
    return Response(status=200)

# Main bot loop
async def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # Attach bot to Flask app for webhook notifications
    app.bot = application.bot

    # Register standard handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Register game command handlers
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

    # Register game button handlers
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

    # Register game text handlers for challenges
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, basketball_text_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bowling_text_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dart_text_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dice_text_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, football_text_handler))

    print("Starting bot...")
    # Run Flask in a separate thread
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=5000))
    flask_thread.start()
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
