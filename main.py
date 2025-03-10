import asyncio
import sqlite3
import nest_asyncio
import requests
import os
import logging
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, Response

# Game imports (these should match your actual game modules)
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

# Set up logging to help you debug if something goes wrong
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Allow nested event loops (needed for Flask + Telegram)
nest_asyncio.apply()

# Bot configuration (use your own BOT_TOKEN if different)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8118951743:AAHT6bOYhmzl98fyKXvkfvez6refrn5dOlU")
NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "86WDA8Y-A7V4Y5Y-N0ETC4V-JXB03GA")
WEBHOOK_URL = "https://casino-bot-41de.onrender.com"

# Database functions to manage users and balances
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

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received /start command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    if not user_exists(user_id):
        with sqlite3.connect('users.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 0.0)", (user_id, username))
            conn.commit()
    text = (
        "📣 How To Start?\n"
        "1. Make sure you have a balance. You can deposit by entering the /balance command.\n"
        "2. Go to one of our groups in @BalticGames directory\n"
        "3. Enter the /dice command and you are ready!\n\n"
        "📣 What games can I play?\n"
        "• 🎲 Dice - /dice\n"
        "• 🎳 Bowling - /bowl\n"
        "• 🎯 Darts - /dart\n"
        "• ⚽️ Football - /football\n"
        "• 🏀 Basketball - /basketball\n"
        "• 🪙 Coinflip - /coin\n"
        "• 🎰 Slot machine - /slots\n"
        "• 🎲 Dice Prediction - /predict\n"
        "• 💣 Mines - /mine\n"
        "• 🐒 Monkey Tower - /tower\n"
        "• 🎰 Roulette  - /roul\n\n"
        "Enjoy the games! 🍀"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    logger.info(f"Sent /start response to chat {update.effective_chat.id}")

async def balance_command(update, context):
    logger.info("Balance command triggered")
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

# Button handler for deposit and withdraw buttons
async def button_handler(update, context):
    query = update.callback_query
    data = query.data
    logger.info(f"Button pressed: {data}")
    chat_id = query.message.chat_id

    if data == "deposit":
        await query.answer("Deposit functionality coming soon!")
    elif data == "withdraw":
        await query.answer()
        await context.bot.send_message(chat_id=chat_id, text="Please enter the amount and your LTC address, e.g., '5.00 LTC123...'")
        context.user_data['expecting_withdrawal_details'] = True
    else:
        await query.answer("Unknown action.")

# Text handler for withdrawal input
async def text_handler(update, context):
    chat_id = update.effective_chat.id
    if context.user_data.get('expecting_withdrawal_details'):
        try:
            amount, address = update.message.text.split()
            amount = float(amount)
            # Placeholder for actual withdrawal (you can add real logic later)
            await context.bot.send_message(chat_id=chat_id, text=f"Withdrawing ${amount:.2f} to {address}")
            context.user_data['expecting_withdrawal_details'] = False
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Invalid input. Please enter amount and address, e.g., '5.00 LTC123...'")
    else:
        await context.bot.send_message(chat_id=chat_id, text="I don’t understand that command.")

# Flask app setup for webhooks
app = Flask(__name__)

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    return Response(status=200)

@app.route('/webhook', methods=['POST'])
def nowpayments_webhook():
    data = request.json
    if data.get('payment_status') == 'finished':
        payment_id = data['payment_id']
        deposit = get_pending_deposit(payment_id)
        if deposit:
            user_id, amount = deposit
            current_balance = get_user_balance(user_id)
            new_balance = current_balance + amount
            update_user_balance(user_id, new_balance)
            remove_pending_deposit(payment_id)
            asyncio.run_coroutine_threadsafe(
                app.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Deposit of {amount} {data['pay_currency'].upper()} confirmed! New balance: ${new_balance:.2f}"
                ),
                loop
            )
    return Response(status=200)

# Run the event loop in a separate thread
def run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Main bot setup
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

    # Game commands
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

    # Game button handlers
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

    # Start the event loop
    loop = asyncio.new_event_loop()
    threading.Thread(target=run_loop, args=(loop,), daemon=True).start()

    # Set Telegram webhook
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram-webhook")

    # Start Flask app
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    asyncio.run(main())
