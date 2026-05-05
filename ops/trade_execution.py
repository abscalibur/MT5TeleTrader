import asyncio
import inspect
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import select

from core.db import SessionLocal
from core.models import InterpretedTrade
from settings import settings

logger = logging.getLogger(__name__)

INVALID_TRADE_UUID = "invalid trade"


class InvalidTradeError(Exception):
    pass


class TradeExecutionError(Exception):
    pass


@dataclass(frozen=True)
class TradeExecutionResult:
    fetched: int
    executed: int
    invalid: int
    failed: int
    skipped: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, int | bool | str]:
        return asdict(self)


@dataclass(frozen=True)
class PendingTrade:
    id: int
    symbol: str
    side: str
    entry_price: Decimal | None
    stop_loss: Decimal | None


@dataclass(frozen=True)
class OrderPlan:
    trade_unique_id: int
    order_type: Literal["market_buy", "market_sell", "limit_buy", "limit_sell"]
    symbol: str
    volume: float
    stop_loss: Decimal
    take_profit: Decimal
    open_price: Decimal | None
    options: dict[str, int | str]


_execution_lock = asyncio.Lock()


async def run_trade_execution_job() -> TradeExecutionResult:
    if _execution_lock.locked():
        return TradeExecutionResult(
            fetched=0,
            executed=0,
            invalid=0,
            failed=0,
            skipped=True,
            detail="Trade execution is already running.",
        )

    if not settings.METAAPI_TOKEN or not settings.METAAPI_ACCOUNT_ID:
        return TradeExecutionResult(
            fetched=0,
            executed=0,
            invalid=0,
            failed=0,
            skipped=True,
            detail="METAAPI_TOKEN and METAAPI_ACCOUNT_ID must be configured.",
        )

    async with _execution_lock:
        pending_trades = await asyncio.to_thread(_list_pending_trades)
        if not pending_trades:
            return TradeExecutionResult(
                fetched=0,
                executed=0,
                invalid=0,
                failed=0,
                detail="No pending interpreted trades.",
            )

        connection = await _open_metaapi_connection()
        try:
            result = await _execute_pending_trades(connection, pending_trades)
        finally:
            await _close_connection(connection)

    logger.info(
        "Trade execution completed: fetched=%s executed=%s invalid=%s failed=%s",
        result.fetched,
        result.executed,
        result.invalid,
        result.failed,
    )
    return result


async def _execute_pending_trades(connection: Any, pending_trades: list[PendingTrade]) -> TradeExecutionResult:
    executed = 0
    invalid = 0
    failed = 0
    volume = float(settings.TRADE_VOLUME)

    for trade in pending_trades:
        trade_unique_id = generate_trade_unique_id()
        plan: OrderPlan | None = None
        price: dict[str, Any] | None = None
        claimed = False
        try:
            price = await connection.get_symbol_price(symbol=trade.symbol)
            plan = build_order_plan(
                trade,
                price,
                trade_unique_id=trade_unique_id,
                volume=volume,
            )

            claimed = await asyncio.to_thread(_mark_trade_uuid_if_pending, trade.id, str(trade_unique_id))
            if not claimed:
                logger.info("Skipping already claimed interpreted_trade_id=%s", trade.id)
                continue

            await submit_order(connection, plan)
            executed += 1
        except InvalidTradeError as exc:
            await asyncio.to_thread(_mark_trade_uuid_if_pending, trade.id, INVALID_TRADE_UUID)
            invalid += 1
            logger.warning("Skipping invalid trade id=%s: %s", trade.id, exc)
        except Exception as exc:
            if claimed:
                await asyncio.to_thread(_clear_trade_uuid_if_value, trade.id, str(trade_unique_id))
            failed += 1
            logger.exception(
                "Trade execution failed for interpreted_trade_id=%s detail=%s price=%s plan=%s",
                trade.id,
                _exception_detail(exc),
                _safe_json(price),
                _safe_json(order_plan_log_context(plan) if plan else None),
            )

    return TradeExecutionResult(
        fetched=len(pending_trades),
        executed=executed,
        invalid=invalid,
        failed=failed,
    )


def build_order_plan(
    trade: PendingTrade,
    price: dict[str, Any],
    *,
    trade_unique_id: int,
    volume: float,
) -> OrderPlan:
    side = trade.side.lower().strip()
    entry_price = _required_decimal(trade.entry_price, "entry price")
    stop_loss = _required_decimal(trade.stop_loss, "stop loss")

    if side == "buy":
        current_price = _price_decimal(price, "ask")
        if current_price <= entry_price:
            order_type: Literal["market_buy", "limit_buy"] = "market_buy"
            open_price = None
            expected_open_price = current_price
        else:
            order_type = "limit_buy"
            open_price = entry_price
            expected_open_price = entry_price
    elif side == "sell":
        current_price = _price_decimal(price, "bid")
        if current_price >= entry_price:
            order_type: Literal["market_sell", "limit_sell"] = "market_sell"
            open_price = None
            expected_open_price = current_price
        else:
            order_type = "limit_sell"
            open_price = entry_price
            expected_open_price = entry_price
    else:
        raise InvalidTradeError(f"unsupported side: {trade.side}")

    take_profit = calculate_take_profit(side, expected_open_price, stop_loss)
    return OrderPlan(
        trade_unique_id=trade_unique_id,
        order_type=order_type,
        symbol=trade.symbol,
        volume=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
        open_price=open_price,
        options={"magic": trade_unique_id, "clientId": metaapi_client_id(trade.symbol, trade_unique_id)},
    )


def calculate_take_profit(side: str, open_price: Decimal, stop_loss: Decimal) -> Decimal:
    if side == "buy":
        if stop_loss >= open_price:
            raise InvalidTradeError("buy stop loss must be below open price")
        # return open_price + (open_price - stop_loss)
        return open_price + 5

    if side == "sell":
        if stop_loss <= open_price:
            raise InvalidTradeError("sell stop loss must be above open price")
        # return open_price - (stop_loss - open_price)
        return open_price - 5

    raise InvalidTradeError(f"unsupported side: {side}")


async def submit_order(connection: Any, plan: OrderPlan) -> Any:
    payload: dict[str, Any] = {
        "symbol": plan.symbol,
        "volume": plan.volume,
        "stop_loss": _float_price(plan.stop_loss),
        "take_profit": _float_price(plan.take_profit),
        "options": plan.options,
    }

    if plan.order_type == "market_buy":
        return await connection.create_market_buy_order(**payload)
    if plan.order_type == "market_sell":
        return await connection.create_market_sell_order(**payload)

    if plan.open_price is None:
        raise TradeExecutionError("pending order plan is missing open price")

    payload["open_price"] = _float_price(plan.open_price)
    if plan.order_type == "limit_buy":
        return await connection.create_limit_buy_order(**payload)
    if plan.order_type == "limit_sell":
        return await connection.create_limit_sell_order(**payload)

    raise TradeExecutionError(f"unsupported order type: {plan.order_type}")


def order_plan_log_context(plan: OrderPlan) -> dict[str, Any]:
    return {
        "trade_unique_id": plan.trade_unique_id,
        "order_type": plan.order_type,
        "symbol": plan.symbol,
        "volume": plan.volume,
        "open_price": _decimal_text(plan.open_price),
        "stop_loss": _decimal_text(plan.stop_loss),
        "take_profit": _decimal_text(plan.take_profit),
        "options": plan.options,
    }


def metaapi_client_id(symbol: str, trade_unique_id: int) -> str:
    compact_symbol = "".join(char for char in symbol.upper() if char.isalnum()) or "TRADE"
    trade_id = str(trade_unique_id)
    max_symbol_length = max(1, 31 - len("MA__") - len(trade_id))
    return f"MA_{compact_symbol[:max_symbol_length]}_{trade_id}"


def generate_trade_unique_id() -> int:
    return uuid.uuid4().int & 0x7FFFFFFF


def _list_pending_trades() -> list[PendingTrade]:
    with SessionLocal() as db:
        trades = list(
            db.execute(
                select(InterpretedTrade)
                .where(InterpretedTrade.trade_uuid.is_(None))
                .order_by(InterpretedTrade.id.asc())
            ).scalars()
        )

    return [
        PendingTrade(
            id=trade.id,
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entryprice,
            stop_loss=trade.stoploss,
        )
        for trade in trades
    ]


def _mark_trade_uuid_if_pending(trade_id: int, trade_uuid: str) -> bool:
    with SessionLocal() as db:
        trade = db.get(InterpretedTrade, trade_id)
        if trade is None or trade.trade_uuid is not None:
            return False

        trade.trade_uuid = trade_uuid
        db.commit()
        return True


def _clear_trade_uuid_if_value(trade_id: int, trade_uuid: str) -> bool:
    with SessionLocal() as db:
        trade = db.get(InterpretedTrade, trade_id)
        if trade is None or trade.trade_uuid != trade_uuid:
            return False

        trade.trade_uuid = None
        db.commit()
        return True


async def _open_metaapi_connection() -> Any:
    from metaapi_cloud_sdk import MetaApi

    api = MetaApi(token=settings.METAAPI_TOKEN)
    account = await api.metatrader_account_api.get_account(settings.METAAPI_ACCOUNT_ID)
    await account.deploy()
    await account.wait_connected()

    connection = account.get_rpc_connection()
    await connection.connect()
    await connection.wait_synchronized()
    return connection


async def _close_connection(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if close is None:
        return

    try:
        close_result = close()
        if inspect.isawaitable(close_result):
            await close_result
    except Exception:
        logger.warning("MetaApi connection close failed", exc_info=True)


def _required_decimal(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise InvalidTradeError(f"{field_name} is missing")

    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidTradeError(f"{field_name} is invalid") from exc

    if not decimal_value.is_finite() or decimal_value <= 0:
        raise InvalidTradeError(f"{field_name} must be positive")

    return decimal_value


def _price_decimal(price: dict[str, Any], key: str) -> Decimal:
    try:
        decimal_value = Decimal(str(price[key]))
    except (KeyError, InvalidOperation) as exc:
        raise TradeExecutionError(f"MetaApi price is missing {key}") from exc

    if not decimal_value.is_finite() or decimal_value <= 0:
        raise TradeExecutionError(f"MetaApi price {key} must be positive")

    return decimal_value


def _float_price(value: Decimal) -> float:
    return float(value)


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _exception_detail(exc: Exception) -> str:
    details = getattr(exc, "details", None)
    if details:
        return _safe_json(details)

    return str(exc)


def _safe_json(value: Any) -> str:
    if value is None:
        return "null"

    try:
        return json.dumps(value, default=str, sort_keys=True)
    except TypeError:
        return str(value)
