# manual_reply_async.py

import asyncio
from telegram import Bot

BOT_TOKEN = "TOKEN"
bot = Bot(token=YOUR_BOT_TOKEN_HERE)

async def send_manual(chat_id: int, text: str):
    """Asynchronous sending of a message to a specific user"""
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        print(f"[✅] The message has been sent to the user {chat_id}\n")
    except Exception as e:
        print(f"[❌] Error when sending: {e}\n")


async def input_loop():
    """Asynchronous input of messages from the console"""
    print("=== Manual message sending mode ===")
    print("Copy the chat_id from the logs main.py and enter the message.")
    print("To exit Ctrl+C\n")

    while True:
        try:
            chat_id_input = await asyncio.to_thread(input, "Enter chat_id: ")
            if not chat_id_input.isdigit():
                print("[❌] The chat_id must be a number.")
                continue

            text_input = await asyncio.to_thread(input, "Enter the response text: ")

            # Waiting for the message to be sent before proceeding to the next input
            await send_manual(int(chat_id_input), text_input)

        except KeyboardInterrupt:
            print("\nExiting manual mode.")
            break


if __name__ == "__main__":
    asyncio.run(input_loop())
