import asyncio
import logging
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, select

from core.AI.trade_signal_parser import LLMRequestError, parse_trade_signal_with_llm
from core.db import SessionLocal
from core.models import Channel, InterpretedTrade, MessageRead
from settings import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradeInterpretationResult:
    fetched: int
    processed: int
    created: int
    updated: int
    deleted: int
    invalid: int
    failed: int
    skipped: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, int | bool | str]:
        return asdict(self)


@dataclass(frozen=True)
class MessageToInterpret:
    channel_id: int
    message_id: int
    message_text: str


@dataclass(frozen=True)
class StoreInterpretationResult:
    processed: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    invalid: int = 0


_interpretation_lock = asyncio.Lock()


async def run_trade_interpretation_job() -> TradeInterpretationResult:
    if _interpretation_lock.locked():
        return TradeInterpretationResult(
            fetched=0,
            processed=0,
            created=0,
            updated=0,
            deleted=0,
            invalid=0,
            failed=0,
            skipped=True,
            detail="Trade interpretation is already running.",
        )

    if not settings.NVIDIA_API_KEY:
        return TradeInterpretationResult(
            fetched=0,
            processed=0,
            created=0,
            updated=0,
            deleted=0,
            invalid=0,
            failed=0,
            skipped=True,
            detail="NVIDIA_API_KEY is not configured.",
        )

    async with _interpretation_lock:
        result = await asyncio.to_thread(_interpret_unprocessed_messages)

    logger.info(
        "Trade interpretation completed: fetched=%s processed=%s created=%s updated=%s deleted=%s invalid=%s failed=%s",
        result.fetched,
        result.processed,
        result.created,
        result.updated,
        result.deleted,
        result.invalid,
        result.failed,
    )
    return result


async def list_interpreted_trades(limit: int = 200) -> list[dict[str, int | str | None]]:
    return await asyncio.to_thread(_list_interpreted_trades, limit)


def _interpret_unprocessed_messages() -> TradeInterpretationResult:
    messages = _list_unprocessed_messages()
    if not messages:
        return TradeInterpretationResult(
            fetched=0,
            processed=0,
            created=0,
            updated=0,
            deleted=0,
            invalid=0,
            failed=0,
            detail="No unprocessed messages.",
        )

    processed = 0
    created = 0
    updated = 0
    deleted = 0
    invalid = 0
    failed = 0

    for message in messages:
        try:
            parsed = parse_trade_signal_with_llm(
                message.message_text,
                api_key=settings.NVIDIA_API_KEY,
                base_url=settings.NVIDIA_BASE_URL,
                model=settings.NVIDIA_MODEL,
                reasoning_effort=settings.NVIDIA_REASONING_EFFORT,
                temperature=settings.NVIDIA_TEMPERATURE,
                max_tokens=settings.NVIDIA_MAX_TOKENS,
                retries=settings.NVIDIA_PARSE_RETRIES,
                timeout_seconds=settings.NVIDIA_PARSE_TIMEOUT_SECONDS,
            )
        except LLMRequestError:
            failed += 1
            logger.exception(
                "Trade interpretation LLM request failed for channel_id=%s message_id=%s",
                message.channel_id,
                message.message_id,
            )
            continue

        try:
            stored = _store_trade_interpretation(message, parsed)
        except Exception:
            failed += 1
            logger.exception(
                "Trade interpretation store failed for channel_id=%s message_id=%s",
                message.channel_id,
                message.message_id,
            )
            continue

        processed += stored.processed
        created += stored.created
        updated += stored.updated
        deleted += stored.deleted
        invalid += stored.invalid

    return TradeInterpretationResult(
        fetched=len(messages),
        processed=processed,
        created=created,
        updated=updated,
        deleted=deleted,
        invalid=invalid,
        failed=failed,
    )


def _list_unprocessed_messages() -> list[MessageToInterpret]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                MessageRead.channel_id,
                MessageRead.message_id,
                MessageRead.message_text,
            )
            .where(MessageRead.processed.is_(False))
            .order_by(MessageRead.message_time.asc(), MessageRead.channel_id, MessageRead.message_id)
        ).all()

    return [
        MessageToInterpret(
            channel_id=int(channel_id),
            message_id=int(message_id),
            message_text=str(message_text),
        )
        for channel_id, message_id, message_text in rows
    ]


def _list_interpreted_trades(limit: int) -> list[dict[str, int | str | None]]:
    bounded_limit = max(1, min(limit, 500))

    with SessionLocal() as db:
        rows = db.execute(
            select(
                InterpretedTrade,
                Channel.name,
                MessageRead.message_time,
                MessageRead.message_text,
            )
            .join(Channel, InterpretedTrade.channel_id == Channel.id)
            .join(
                MessageRead,
                and_(
                    InterpretedTrade.channel_id == MessageRead.channel_id,
                    InterpretedTrade.message_id == MessageRead.message_id,
                ),
            )
            .order_by(MessageRead.message_time.desc(), InterpretedTrade.id.desc())
            .limit(bounded_limit)
        ).all()

        return [
            _serialize_interpreted_trade(trade, channel_name, message_time, message_text)
            for trade, channel_name, message_time, message_text in rows
        ]


def _serialize_interpreted_trade(
    trade: InterpretedTrade,
    channel_name: str,
    message_time: Any,
    message_text: str,
) -> dict[str, int | str | None]:
    return {
        "id": trade.id,
        "channel_id": trade.channel_id,
        "channel_name": channel_name,
        "message_id": trade.message_id,
        "trade_uuid": trade.trade_uuid,
        "message_time": message_time.isoformat(),
        "message_text": message_text,
        "symbol": trade.symbol,
        "side": trade.side,
        "entry_price": str(trade.entryprice) if trade.entryprice is not None else None,
        "stoploss": str(trade.stoploss),
    }


def _store_trade_interpretation(
    message: MessageToInterpret,
    parsed: dict[str, Any],
) -> StoreInterpretationResult:
    with SessionLocal() as db:
        message_read = db.get(MessageRead, (message.channel_id, message.message_id))
        if message_read is None or message_read.processed:
            return StoreInterpretationResult()

        existing_trades = list(
            db.execute(
                select(InterpretedTrade)
                .where(
                    InterpretedTrade.channel_id == message.channel_id,
                    InterpretedTrade.message_id == message.message_id,
                )
                .order_by(InterpretedTrade.id.asc())
            ).scalars()
        )

        if parsed.get("error") is False:
            used_existing_ids: set[int] = set()
            created = 0
            updated = 0

            for trade in parsed["trades"]:
                symbol = str(trade["symbol"])
                side = str(trade["side"])
                entryprice = Decimal(str(trade["entry_price"]))
                stoploss = Decimal(str(trade["stop_loss"]))
                existing_trade = _find_reusable_trade(existing_trades, used_existing_ids, entryprice)

                if existing_trade is None:
                    db.add(
                        InterpretedTrade(
                            channel_id=message.channel_id,
                            message_id=message.message_id,
                            symbol=symbol,
                            side=side,
                            entryprice=entryprice,
                            stoploss=stoploss,
                        )
                    )
                    created += 1
                    continue

                used_existing_ids.add(existing_trade.id)
                if _trade_changed(existing_trade, symbol, side, entryprice, stoploss):
                    existing_trade.symbol = symbol
                    existing_trade.side = side
                    existing_trade.entryprice = entryprice
                    existing_trade.stoploss = stoploss
                    updated += 1

            deleted = 0
            for existing_trade in existing_trades:
                if existing_trade.id not in used_existing_ids:
                    db.delete(existing_trade)
                    deleted += 1

            message_read.processed = True
            db.commit()
            return StoreInterpretationResult(
                processed=1,
                created=created,
                updated=updated,
                deleted=deleted,
            )

        deleted = 0
        for existing_trade in existing_trades:
            db.delete(existing_trade)
            deleted += 1

        message_read.processed = True
        db.commit()
        return StoreInterpretationResult(processed=1, deleted=deleted, invalid=1)


def _find_reusable_trade(
    existing_trades: list[InterpretedTrade],
    used_existing_ids: set[int],
    entryprice: Decimal,
) -> InterpretedTrade | None:
    for existing_trade in existing_trades:
        if existing_trade.id not in used_existing_ids and existing_trade.entryprice == entryprice:
            return existing_trade

    for existing_trade in existing_trades:
        if existing_trade.id not in used_existing_ids:
            return existing_trade

    return None


def _trade_changed(
    trade: InterpretedTrade,
    symbol: str,
    side: str,
    entryprice: Decimal,
    stoploss: Decimal,
) -> bool:
    return (
        trade.symbol != symbol
        or trade.side != side
        or trade.entryprice != entryprice
        or trade.stoploss != stoploss
    )
