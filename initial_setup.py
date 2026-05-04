import asyncio
import json
from pathlib import Path

from core.telegram.client import TelegramConnector


CHANNELS_OUTPUT_PATH = Path("runtime/channels.json")


async def main():
    # Initialize the TelegramConnector
    connector = TelegramConnector()

    # Connect to Telegram and fetch channels
    await connector.client.start(phone=connector.phone_number)
    try:
        channels = []
        async for dialog in connector.client.iter_dialogs():
            if dialog.is_channel:
                channels.append({
                    "name": dialog.name,
                    "id": dialog.id,
                    "enabled": False,
                })

        CHANNELS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHANNELS_OUTPUT_PATH.write_text(
            json.dumps(channels, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Recorded {len(channels)} channels to {CHANNELS_OUTPUT_PATH}")
    finally:
        await connector.client.disconnect()


asyncio.run(main())
