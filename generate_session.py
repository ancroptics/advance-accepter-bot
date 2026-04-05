#!/usr/bin/env python3
"""Generate a Telethon StringSession for the bot.

Run this locally:
    pip install telethon
    python generate_session.py

It will ask for your API ID, API Hash (from https://my.telegram.org),
and your phone number. After verification, it prints a session string
to set as TELETHON_SESSION_STRING env var.
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    print("=== Telethon Session Generator ===")
    print("Get API ID & Hash from: https://my.telegram.org/apps\n")

    api_id = input("Enter API ID: ").strip()
    api_hash = input("Enter API Hash: ").strip()

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start()

    session_string = client.session.save()
    print(f"\n✅ Session generated!\n")
    print(f"Set these environment variables on Render:\n")
    print(f"  TELETHON_API_ID={api_id}")
    print(f"  TELETHON_API_HASH={api_hash}")
    print(f"  TELETHON_SESSION_STRING={session_string}")
    print(f"\n⚠️  Keep the session string secret — it grants access to your Telegram account!")

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
