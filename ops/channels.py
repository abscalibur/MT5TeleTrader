import asyncio
import logging
from dataclasses import asdict, dataclass

from sqlalchemy import select

from core.db import SessionLocal
from core.models import Channel
from core.telegram.client import TelegramConnector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelSyncResult:
    fetched: int
    created: int
    updated: int
    skipped: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, int | bool | str]:
        return asdict(self)


_sync_lock = asyncio.Lock()


async def fetch_available_telegram_channels() -> list[dict[str, int | str]]:
    connector = TelegramConnector()

    await connector.client.connect()
    try:
        if not await connector.client.is_user_authorized():
            raise RuntimeError(
                "Telegram session is not authorized. Run initial_setup.py once to create the session."
            )

        channels: list[dict[str, int | str]] = []
        async for dialog in connector.get_channels():
            if not dialog.is_channel:
                continue

            channels.append(
                {
                    "id": int(dialog.id),
                    "name": dialog.name or str(dialog.id),
                }
            )

        return sorted(channels, key=lambda channel: str(channel["name"]).casefold())
    finally:
        await connector.client.disconnect()


async def sync_telegram_channels() -> ChannelSyncResult:
    channels = await fetch_available_telegram_channels()
    return await asyncio.to_thread(_store_channels, channels)


async def run_channel_sync_job() -> ChannelSyncResult:
    if _sync_lock.locked():
        return ChannelSyncResult(
            fetched=0,
            created=0,
            updated=0,
            skipped=True,
            detail="Channel sync is already running.",
        )

    async with _sync_lock:
        try:
            result = await sync_telegram_channels()
        except Exception:
            logger.exception("Telegram channel sync failed")
            raise

        logger.info(
            "Telegram channel sync completed: fetched=%s created=%s updated=%s",
            result.fetched,
            result.created,
            result.updated,
        )
        return result


async def list_channels() -> list[dict[str, int | str | bool]]:
    return await asyncio.to_thread(_list_channels)


async def set_channel_enabled(
    channel_id: int,
    enabled: bool,
) -> dict[str, int | str | bool] | None:
    return await asyncio.to_thread(_set_channel_enabled, channel_id, enabled)


def _store_channels(channels: list[dict[str, int | str]]) -> ChannelSyncResult:
    created = 0
    updated = 0

    with SessionLocal() as db:
        for channel_data in channels:
            channel_id = int(channel_data["id"])
            name = str(channel_data["name"])
            channel = db.get(Channel, channel_id)

            if channel is None:
                db.add(Channel(id=channel_id, name=name, enabled=False))
                created += 1
                continue

            if channel.name != name:
                channel.name = name
                updated += 1

        db.commit()

    return ChannelSyncResult(fetched=len(channels), created=created, updated=updated)


def _list_channels() -> list[dict[str, int | str | bool]]:
    with SessionLocal() as db:
        channels = db.execute(select(Channel).order_by(Channel.name)).scalars().all()
        return [_serialize_channel(channel) for channel in channels]


def _set_channel_enabled(
    channel_id: int,
    enabled: bool,
) -> dict[str, int | str | bool] | None:
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if channel is None:
            return None

        channel.enabled = enabled
        db.commit()
        db.refresh(channel)
        return _serialize_channel(channel)


def _serialize_channel(channel: Channel) -> dict[str, int | str | bool]:
    return {
        "id": channel.id,
        "name": channel.name,
        "enabled": channel.enabled,
    }
