from datetime import datetime, timedelta, timezone

from settings import settings
from telethon import TelegramClient



class TelegramConnector:
    def __init__(self):
        self.api_id = settings.TELEGRAM_API_ID
        self.api_hash = settings.TELEGRAM_API_HASH
        self.session_name = settings.TELEGRAM_SESSION_NAME
        self.phone_number = settings.PHONE_NUMBER
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)

    async def first_auth(self) -> None:
        await self.client.start(phone=self.phone_number)
        print("Telegram client authenticated successfully.")
        await self.client.disconnect()

    async def get_channels(self):
        async for dialog in self.client.iter_dialogs():
            yield dialog

    async def get_recent_messages_for_channel(
        self,
        channel_id: str,
        limit=10,
        minutes=30
    ):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        entity = await self.client.get_entity(channel_id)

        async for message in self.client.iter_messages(entity, limit=limit):
            message_date = self._as_utc(message.date)
            if message_date < cutoff:
                break

            yield message

    async def fetch_message_after(self, channel_id, message_id):
        entity = await self.client.get_entity(channel_id)

        async for message in self.client.iter_messages(
            entity,
            min_id=message_id,
            reverse=True,
            limit=1,
        ):
            return message

        return None

    @staticmethod
    def _as_utc(date):
        if date.tzinfo is None:
            return date.replace(tzinfo=timezone.utc)

        return date.astimezone(timezone.utc)
