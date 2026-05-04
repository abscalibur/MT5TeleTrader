import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from core.db import SessionLocal
from core.models import Channel, MessageRead
from core.telegram.client import TelegramConnector
from settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MessageSyncResult:
    channels: int
    fetched: int
    created: int
    updated: int
    failed_channels: int = 0
    skipped: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, int | bool | str]:
        return asdict(self)


_sync_lock = asyncio.Lock()


async def sync_telegram_messages() -> MessageSyncResult:
    channels = await asyncio.to_thread(_list_enabled_channels)
    if not channels:
        return MessageSyncResult(
            channels=0,
            fetched=0,
            created=0,
            updated=0,
            detail="No enabled channels.",
        )

    messages, failed_channels = await fetch_enabled_channel_messages(channels)
    created, updated = await asyncio.to_thread(_store_messages, messages)

    return MessageSyncResult(
        channels=len(channels),
        fetched=len(messages),
        created=created,
        updated=updated,
        failed_channels=failed_channels,
    )


async def run_message_sync_job() -> MessageSyncResult:
    if _sync_lock.locked():
        return MessageSyncResult(
            channels=0,
            fetched=0,
            created=0,
            updated=0,
            skipped=True,
            detail="Message sync is already running.",
        )

    async with _sync_lock:
        try:
            result = await sync_telegram_messages()
        except Exception:
            logger.exception("Telegram message sync failed")
            raise

        logger.info(
            "Telegram message sync completed: channels=%s fetched=%s created=%s updated=%s failed_channels=%s",
            result.channels,
            result.fetched,
            result.created,
            result.updated,
            result.failed_channels,
        )
        return result


async def list_messages_read(limit: int = 200) -> list[dict[str, int | str | bool]]:
    return await asyncio.to_thread(_list_messages_read, limit)


async def fetch_enabled_channel_messages(
    channels: list[dict[str, int | str]],
) -> tuple[list[dict[str, int | str | datetime]], int]:
    connector = TelegramConnector()

    await connector.client.connect()
    try:
        if not await connector.client.is_user_authorized():
            raise RuntimeError(
                "Telegram session is not authorized. Run initial_setup.py once to create the session."
            )

        messages: list[dict[str, int | str | datetime]] = []
        failed_channels = 0

        for channel in channels:
            channel_id = int(channel["id"])
            try:
                async for message in connector.get_recent_messages_for_channel(
                    channel_id,
                    limit=settings.MESSAGE_SYNC_LIMIT_PER_CHANNEL,
                    minutes=settings.MESSAGE_SYNC_LOOKBACK_MINUTES,
                ):
                    message_id = getattr(message, "id", None)
                    message_date = getattr(message, "date", None)
                    if message_id is None or message_date is None:
                        continue

                    messages.append(
                        {
                            "channel_id": channel_id,
                            "message_id": int(message_id),
                            "message_text": getattr(message, "message", None)
                            or getattr(message, "text", None)
                            or "",
                            "message_time": _as_utc(message_date),
                        }
                    )
            except Exception:
                failed_channels += 1
                logger.exception(
                    "Telegram message fetch failed for channel_id=%s name=%s",
                    channel_id,
                    channel.get("name", ""),
                )

        return messages, failed_channels
    finally:
        await connector.client.disconnect()


def _list_enabled_channels() -> list[dict[str, int | str]]:
    with SessionLocal() as db:
        channels = db.execute(
            select(Channel).where(Channel.enabled.is_(True)).order_by(Channel.name)
        ).scalars().all()

        return [{"id": channel.id, "name": channel.name} for channel in channels]


def _list_messages_read(limit: int) -> list[dict[str, int | str | bool]]:
    bounded_limit = max(1, min(limit, 500))

    with SessionLocal() as db:
        rows = db.execute(
            select(MessageRead, Channel.name)
            .join(Channel, MessageRead.channel_id == Channel.id)
            .order_by(
                MessageRead.message_time.desc(),
                MessageRead.channel_id,
                MessageRead.message_id.desc(),
            )
            .limit(bounded_limit)
        ).all()

        return [
            _serialize_message_read(message_read, channel_name)
            for message_read, channel_name in rows
        ]


def _serialize_message_read(
    message_read: MessageRead,
    channel_name: str,
) -> dict[str, int | str | bool]:
    return {
        "channel_id": message_read.channel_id,
        "channel_name": channel_name,
        "message_id": message_read.message_id,
        "message_text": message_read.message_text,
        "message_time": _as_utc(message_read.message_time).isoformat(),
        "processed": message_read.processed,
    }


def _store_messages(messages: list[dict[str, int | str | datetime]]) -> tuple[int, int]:
    created = 0
    updated = 0

    with SessionLocal() as db:
        for message_data in messages:
            channel_id = int(message_data["channel_id"])
            message_id = int(message_data["message_id"])
            message_text = str(message_data["message_text"])
            message_time = _as_utc(message_data["message_time"])

            message_read = db.get(MessageRead, (channel_id, message_id))
            if message_read is None:
                db.add(
                    MessageRead(
                        channel_id=channel_id,
                        message_id=message_id,
                        message_text=message_text,
                        message_time=message_time,
                    )
                )
                created += 1
                continue

            if (
                message_read.message_text != message_text
                or _as_utc(message_read.message_time) != message_time
            ):
                message_read.message_text = message_text
                message_read.message_time = message_time
                message_read.processed = False
                updated += 1

        db.commit()

    return created, updated


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)
