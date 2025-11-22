Beta-version

**An intermediary bot for anonymous or semi-anonymous communication between users and the administrator.
It supports forwarding messages and files, maintaining a database, blocking users, antivirus scanning of files, and a full-fledged administrative interface.**

👤 **For users**
* The /start command is registration and welcome at the first launch.
* Sending any messages and most types of files (photo, document, audio, voice, video, sticker).
* Checking files by extensions (whitelist).
* Guaranteed message: "The message has been delivered to the administrator."
* The user does not see the admin and writes strictly through the bot.


🛡 **For the administrator**

The administrator fully controls the bot:
Viewing incoming messages
```/inbox```
Shows the last 30 messages indicating:
* message ID
* user's alias
* direction (in/out)
* type and content

Messages are automatically cut to avoid exceeding the Telegram limit.

**Response to the user**
```/reply User#N response text...```
Sends a text message back to the user.

**Forwarding a file from the message archive to the user**
```/send User#N MESSAGE_ID```
The bot will find the file by ID and forward it to the user.

**Uploading the file to the server + checking with antivirus (ClamAV)**
```/fetch MESSAGE_ID```
* Downloads the file to QUARANTINE_DIR
* Performs verification via clamscan
* Notifies the administrator of the result
  Requires the variable ALLOW_DOWNLOAD=1.

**Blocking the user**
```/block User#N [reason]```

**Blocking**
```/unblock User#N```

**The database**
SQLite is used (the file is bot.db or the path from the environment variable).

The users table:
```
id            internal ID
chat_id       Telegram chat ID
alias         user's alias (if installed)
first_start   is this the first launch
```

The messages table:
```
Saves:
text
file_id
file type
file name
direction (in/out)
timestamp
```

The blocked_users table:
Used by the locking system.

📁 **File upload restrictions**
The bot accepts:
```photo, document, audio, voice, video, sticker```
Allowed document extensions:
```.pdf .txt .md .jpg .jpeg .png .mp4 .mp3 .ogg .sql```
Files that violate the policy are rejected.

Environment variables
```
BOT_TOKEN        Telegram bot token
ADMIN_ID         Telegram ID of the administrator
DB_PATH          database path (bot.db by default)
QUARANTINE_DIR   directory for downloaded files
ALLOW_DOWNLOAD   1 — allow file downloads, otherwise it is prohibited
```

**WARRING**
For everything to work correctly, you need to replace the values:
* YOUR_BOT_TOKEN_HERE
* YOUR_TG_ACCOUNT_ID
* "your system username without quotese"
* /path/to/script/folder/
* /path/to/script/folder/main.py

on your own data.

These values are in the files:
* Dockerfile
* manual_reply.py
* systemd unit.ini
* token.env

**INSTALLATION**

**To launch the bot:**

```
cd /path/to/script/folder/
source venv/bin/activate
export BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
export ADMIN_ID="YOUR_TG_ACCOUNT_ID"
export ALLOW_DOWNLOAD="1"
python main.py
```

In a separate terminal:

```
cd /path/to/script/folder/
source venv/bin/activate
python manual_reply.py
```

**Checking the database contents:**

```
cd /path/to/script/folder/
source venv/bin/activate
sqlite3 bot.db
```

In the interactive console:

```
.tables
SELECT * FROM users;
```

Exit from sqlite3:

```
.quit
```

**P.S.**
For the bot to work continuously, the device on which the script is running must either be permanently turned on (as a server), or you must rent servers.
If you don't need the bot to work 24/7, then run the script at the right time.
