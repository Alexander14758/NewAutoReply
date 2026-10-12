import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")


async def main():
    print("=" * 50)
    print("  Telegram UserBot — Login Script")
    print("=" * 50)

    if not API_ID or not API_HASH:
        print("\nERROR: API_ID and API_HASH must be set as Replit Secrets.")
        print("Go to: Tools > Secrets, and add them there.")
        return

    print("\nStarting login. You will be asked for your phone number.")
    print("Telegram will send you a verification code.\n")

    client = TelegramClient(StringSession(), int(API_ID), API_HASH)
    await client.start()

    session_string = client.session.save()

    print("\n" + "=" * 50)
    print("LOGIN SUCCESSFUL!")
    print("=" * 50)
    print("\nYour session string (copy everything between the lines):")
    print("-" * 50)
    print(session_string)
    print("-" * 50)
    print("\nNext step:")
    print("1. Copy the session string above")
    print("2. Go to Tools > Secrets in Replit")
    print("3. Add a secret named: TELEGRAM_SESSION")
    print("4. Paste the string as the value")
    print("5. Then run main.py\n")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
