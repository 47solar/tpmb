#!/usr/bin/env python3

import os
import sqlite3
import logging
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from telegram import Update, MessageEntity
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)

import logging

logging.basicConfig(
    level=logging.INFO,              
    format='%(asctime)s [%(levelname)s] %(message)s',  
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0")) 
DB_PATH = os.environ.get("DB_PATH", "bot.db")
QUARANTINE_DIR = os.environ.get("QUARANTINE_DIR", "/tmp/bot_quarantine")
ALLOW_DOWNLOAD = os.environ.get("ALLOW_DOWNLOAD", "0") == "1"


ALLOWED_FILE_TYPES = {
    "photo",        
    "document",   
    "audio",
    "voice",
    "video",
    "sticker",
}

ALLOWED_DOCUMENT_EXTS = {
    ".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".mp4", ".mp3", ".ogg", ".sql"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      chat_id INTEGER UNIQUE,
      alias TEXT
    )""")

    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    if "first_start" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN first_start INTEGER DEFAULT 1")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      text TEXT,
      file_id TEXT,
      file_type TEXT,
      filename TEXT,
      ts DATETIME DEFAULT CURRENT_TIMESTAMP,
      direction TEXT,
      FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS blocked_users (
      user_id INTEGER PRIMARY KEY,
      reason TEXT,
      ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.commit()
    conn.close()

    Path(QUARANTINE_DIR).mkdir(parents=True, exist_ok=True)

def get_or_create_user(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, chat_id, first_start FROM users WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute("INSERT INTO users (chat_id, first_start) VALUES (?, ?)", (chat_id, 1))
        conn.commit()
        cur.execute("SELECT id, chat_id, first_start FROM users WHERE chat_id=?", (chat_id,))
        row = cur.fetchone()

    conn.close()
    return {"id": row[0], "chat_id": row[1], "first_start": row[2]}

def save_message(user_id: int, text: Optional[str]=None, file_id: Optional[str]=None,
                 file_type: Optional[str]=None, filename: Optional[str]=None, direction: str='in'):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (user_id, text, file_id, file_type, filename, direction) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, text, file_id, file_type, filename, direction)
    )
    conn.commit()
    conn.close()

def find_user_by_alias(alias: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, chat_id FROM users WHERE alias = ?", (alias,))
    row = cur.fetchone()
    conn.close()
    return row  

def is_blocked(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM blocked_users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row)

def block_user(user_id: int, reason: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO blocked_users (user_id, reason) VALUES (?, ?)", (user_id, reason))
    conn.commit()
    conn.close()

def unblock_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def safe_filename_from_message(msg) -> Optional[str]:
    if msg.document and msg.document.file_name:
        return msg.document.file_name
    return None

def document_ext_allowed(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_DOCUMENT_EXTS

def update_user_first_start(user_id, value: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET first_start = ? WHERE id = ?", (value, user_id))
    conn.commit()
    conn.close()

def mark_user_started(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET first_start=0 WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    user = get_or_create_user(chat_id)

    if user["first_start"] == 1:
        await update.message.reply_text(
            """Hi. You can use this bot to message me about a purchase."""
        )

        mark_user_started(chat_id)

    else:
        await update.message.reply_text("You have launched the bot again.")

user_messages = {}  # chat_id -> last message

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg is None:
        return

    chat_id = msg.chat.id
    text = msg.text or "<no text>"

    user_row = get_or_create_user(chat_id)
    user_db_id = user_row["id"]
    alias = user_row.get("alias", "<without alias>")

    user_messages[chat_id] = text

    username = msg.from_user.username if msg.from_user.username else "<without username>"
    logging.info(f"[USER {chat_id} | {username}] {text}")

    save_message(user_db_id, text=text, direction='in')

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"New message from {chat_id} | {username}: {text}"
        )
    except Exception as e:
        logging.error(f"Error notifying admin: {e}")

    filename = safe_filename_from_message(msg)
    file_id = None
    file_type = None

    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "document"
    elif msg.audio:
        file_id = msg.audio.file_id
        file_type = "audio"
    elif msg.voice:
        file_id = msg.voice.file_id
        file_type = "voice"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
    elif msg.sticker:
        file_id = msg.sticker.file_id
        file_type = "sticker"

    # Security
    if file_type and file_type not in ALLOWED_FILE_TYPES:
        await msg.reply_text("This file type is not supported.")
        return
    if file_type == "document" and filename:
        if not document_ext_allowed(filename):
            await msg.reply_text("File extension is not allowed.")
            return

    # Save metadata
    text = msg.text or msg.caption or None
    save_message(user_db_id, text=text, file_id=file_id, file_type=file_type, filename=filename, direction='in')

    notify_text = f"New message from {alias} ({chat_id if False else 'anonymously'}):\n"
    if text:
        notify_text += text

    try:
        if file_type == "photo":
            await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=file_id, caption=f"От {alias}")
        elif file_type == "document":
            await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)
            await context.bot.send_document(chat_id=ADMIN_ID, document=file_id, filename=filename)
        elif file_type:
            await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)
            if file_type == "audio":
                await context.bot.send_audio(chat_id=ADMIN_ID, audio=file_id)
            elif file_type == "voice":
                await context.bot.send_voice(chat_id=ADMIN_ID, voice=file_id)
            elif file_type == "video":
                await context.bot.send_video(chat_id=ADMIN_ID, video=file_id)
            elif file_type == "sticker":
                await context.bot.send_sticker(chat_id=ADMIN_ID, sticker=file_id)
        else:
            await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text)
    except Exception as e:
        logger.exception("Error notifying admin: %s", e)

    # Confirmation to the user
    await msg.reply_text("The message has been delivered to the administrator. Please wait for a response.")

async def admin_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
      SELECT m.id, u.alias, m.direction, m.text, m.file_type, m.filename, m.ts
      FROM messages m JOIN users u ON m.user_id = u.id
      ORDER BY m.ts DESC LIMIT 30
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await context.bot.send_message(chat_id=ADMIN_ID, text="No messages.")
        return

    text_lines = []
    for r in rows:
        mid, alias, direction, mtext, ftype, fname, ts = r
        ts_str = ts if isinstance(ts, str) else str(ts)
        s = f"[{mid}] {alias} {direction} {ts_str}\n"
        if mtext:
            s += mtext[:300] + "\n"
        elif ftype:
            s += f"<{ftype}> {fname or ''}\n"
        s += "----\n"
        text_lines.append(s)

    # Telegram has a limit on the length of a message, set in parts
    chunk = ""
    for part in text_lines:
        if len(chunk) + len(part) > 3800:
            await context.bot.send_message(chat_id=ADMIN_ID, text=chunk)
            chunk = part
        else:
            chunk += part
    if chunk:
        await context.bot.send_message(chat_id=ADMIN_ID, text=chunk)

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /reply User#N reply text.")
        return
    alias = context.args[0]
    reply_text = " ".join(context.args[1:])
    row = find_user_by_alias(alias)
    if not row:
        await update.message.reply_text("User not found.")
        return
    user_db_id, chat_id = row
    save_message(user_db_id, text=reply_text, file_id=None, file_type=None, filename=None, direction='out')
    try:
        await context.bot.send_message(chat_id=chat_id, text=reply_text)
        await update.message.reply_text("Sent.")
    except Exception as e:
        logger.exception("Error sending message to user: %s", e)
        await update.message.reply_text("Error sending.")

async def admin_send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /send User#N MESSAGE_ID")
        return
    alias = context.args[0]
    msg_id = context.args[1]
    row = find_user_by_alias(alias)
    if not row:
        await update.message.reply_text("User not found.")
        return
    user_db_id, chat_id = row
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_id, file_type, filename FROM messages WHERE id = ? AND user_id = ?", (msg_id, user_db_id))
    r = cur.fetchone()
    conn.close()
    if not r:
        await update.message.reply_text("Message/file not found.")
        return
    file_id, file_type, filename = r
    try:
        if file_type == "photo":
            await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=f"From the administrator")
        elif file_type == "document":
            await context.bot.send_document(chat_id=chat_id, document=file_id, filename=filename)
        elif file_type == "audio":
            await context.bot.send_audio(chat_id=chat_id, audio=file_id)
        elif file_type == "voice":
            await context.bot.send_voice(chat_id=chat_id, voice=file_id)
        elif file_type == "video":
            await context.bot.send_video(chat_id=chat_id, video=file_id)
        elif file_type == "sticker":
            await context.bot.send_sticker(chat_id=chat_id, sticker=file_id)
        else:
            await update.message.reply_text("File type not supported.")
            return
        save_message(user_db_id, text=f"file sent (msg {msg_id})", file_id=file_id, file_type=file_type, filename=filename, direction='out')
        await update.message.reply_text("The file has been sent.")
    except Exception as e:
        logger.exception("Error sending file: %s", e)
        await update.message.reply_text("Error sending file.")

# Secure file download in quarantine (optional)
async def admin_fetch_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /fetch MESSAGE_ID")
        return
    msg_id = context.args[0]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_id, file_type, filename FROM messages WHERE id = ?", (msg_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        await update.message.reply_text("Message not found.")
        return
    file_id, file_type, filename = r
    if not file_id:
        await update.message.reply_text("This message has no file.")
        return
    if not ALLOW_DOWNLOAD:
        await update.message.reply_text("Download is disabled on the server (ALLOW_DOWNLOAD=0).")
        return

    safe_name = filename or f"{file_type}_{msg_id}"
    safe_path = Path(QUARANTINE_DIR) / f"{msg_id}_{safe_name}"
    try:
        f = await context.bot.get_file(file_id)
        await f.download_to_drive(custom_path=str(safe_path))
        await update.message.reply_text(f" {safe_path}")
    except Exception as e:
        logger.exception("File downloaded to quarantine: %s", e)
        await update.message.reply_text("Error downloading file.")
        return

    try:
        res = subprocess.run(["clamscan", "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            scan = subprocess.run(["clamscan", "--infected", "--no-summary", str(safe_path)],
                                   capture_output=True, text=True)
            if scan.returncode == 1:
                # Find viruses
                await update.message.reply_text(f"ClamAV: Possible infection!\n{scan.stdout}\n{scan.stderr}")
            else:
                await update.message.reply_text("ClamAV: Purely.")
        else:
            await update.message.reply_text("ClamAV not found or not available on the server.")
    except FileNotFoundError:
        await update.message.reply_text("ClamAV not installed, check skipped.")
    except Exception as e:
        logger.exception("ClamAV startup error: %s", e)
        await update.message.reply_text("ClamAV verification error.")

# Block/unblock
async def admin_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /block User#N [reason]")
        return
    alias = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    row = find_user_by_alias(alias)
    if not row:
        await update.message.reply_text("User not found.")
        return
    user_db_id, chat_id = row
    block_user(user_db_id, reason)
    await update.message.reply_text(f"{alias} blocked. Cause: {reason}")

async def admin_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /unblock User#N")
        return
    alias = context.args[0]
    row = find_user_by_alias(alias)
    if not row:
        await update.message.reply_text("User not found.")
        return
    user_db_id, chat_id = row
    unblock_user(user_db_id)
    await update.message.reply_text(f"{alias} unblocked.")

def main():
    if not BOT_TOKEN or ADMIN_ID == 0:
        logger.error("BOT_TOKEN or ADMIN_ID are not set in the environment variables.")
        return
    init_db()
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("inbox", admin_inbox))
app.add_handler(CommandHandler("reply", admin_reply))
app.add_handler(CommandHandler("send", admin_send_file))
app.add_handler(CommandHandler("fetch", admin_fetch_file))
app.add_handler(CommandHandler("block", admin_block))
app.add_handler(CommandHandler("unblock", admin_unblock))

app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message))

logger.info("Bot started")

app.run_polling()

if __name__ == "__main__":
    main()
