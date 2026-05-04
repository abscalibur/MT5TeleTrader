import asyncio
import unittest
from decimal import Decimal
from unittest.mock import patch

from ops import trade_execution
from ops.trade_execution import (
    INVALID_TRADE_UUID,
    InvalidTradeError,
    PendingTrade,
    build_order_plan,
    metaapi_client_id,
    submit_order,
)


class FakeMetaApiConnection:
    def __init__(self, price: dict | None = None, fail_orders: bool = False) -> None:
        self.price = price or {"bid": 2400, "ask": 2400.5}
        self.fail_orders = fail_orders
        self.calls: list[tuple[str, dict]] = []

    async def get_symbol_price(self, **kwargs):
        return self.price

    async def create_market_buy_order(self, **kwargs):
        if self.fail_orders:
            raise RuntimeError("order failed")
        self.calls.append(("market_buy", kwargs))
        return {"stringCode": "OK"}

    async def create_market_sell_order(self, **kwargs):
        if self.fail_orders:
            raise RuntimeError("order failed")
        self.calls.append(("market_sell", kwargs))
        return {"stringCode": "OK"}

    async def create_limit_buy_order(self, **kwargs):
        if self.fail_orders:
            raise RuntimeError("order failed")
        self.calls.append(("limit_buy", kwargs))
        return {"stringCode": "OK"}

    async def create_limit_sell_order(self, **kwargs):
        if self.fail_orders:
            raise RuntimeError("order failed")
        self.calls.append(("limit_sell", kwargs))
        return {"stringCode": "OK"}


class TradeExecutionPlanningTests(unittest.TestCase):
    def test_buy_market_uses_ask_without_open_price(self) -> None:
        plan = build_order_plan(
            pending_trade(side="buy", entry_price="2400", stop_loss="2390"),
            {"bid": 2397.5, "ask": 2398},
            trade_unique_id=123,
            volume=0.01,
        )

        self.assertEqual(plan.order_type, "market_buy")
        self.assertIsNone(plan.open_price)
        self.assertEqual(plan.take_profit, Decimal("2406"))
        self.assertEqual(plan.options, {"magic": 123, "clientId": "MA_XAUUSD_123"})

        connection = FakeMetaApiConnection()
        asyncio.run(submit_order(connection, plan))

        method, payload = connection.calls[0]
        self.assertEqual(method, "market_buy")
        self.assertNotIn("open_price", payload)
        self.assertEqual(payload["options"], {"magic": 123, "clientId": "MA_XAUUSD_123"})

    def test_buy_limit_uses_entry_price(self) -> None:
        plan = build_order_plan(
            pending_trade(side="buy", entry_price="2400", stop_loss="2390"),
            {"bid": 2401.5, "ask": 2402},
            trade_unique_id=456,
            volume=0.01,
        )

        self.assertEqual(plan.order_type, "limit_buy")
        self.assertEqual(plan.open_price, Decimal("2400"))
        self.assertEqual(plan.take_profit, Decimal("2410"))

        connection = FakeMetaApiConnection()
        asyncio.run(submit_order(connection, plan))

        method, payload = connection.calls[0]
        self.assertEqual(method, "limit_buy")
        self.assertEqual(payload["open_price"], 2400.0)

    def test_sell_market_uses_bid_without_open_price(self) -> None:
        plan = build_order_plan(
            pending_trade(side="sell", entry_price="2400", stop_loss="2410"),
            {"bid": 2402, "ask": 2402.5},
            trade_unique_id=789,
            volume=0.01,
        )

        self.assertEqual(plan.order_type, "market_sell")
        self.assertIsNone(plan.open_price)
        self.assertEqual(plan.take_profit, Decimal("2394"))

        connection = FakeMetaApiConnection()
        asyncio.run(submit_order(connection, plan))

        method, payload = connection.calls[0]
        self.assertEqual(method, "market_sell")
        self.assertNotIn("open_price", payload)

    def test_sell_limit_uses_entry_price(self) -> None:
        plan = build_order_plan(
            pending_trade(side="sell", entry_price="2400", stop_loss="2410"),
            {"bid": 2398, "ask": 2398.5},
            trade_unique_id=321,
            volume=0.01,
        )

        self.assertEqual(plan.order_type, "limit_sell")
        self.assertEqual(plan.open_price, Decimal("2400"))
        self.assertEqual(plan.take_profit, Decimal("2390"))

        connection = FakeMetaApiConnection()
        asyncio.run(submit_order(connection, plan))

        method, payload = connection.calls[0]
        self.assertEqual(method, "limit_sell")
        self.assertEqual(payload["open_price"], 2400.0)

    def test_invalid_buy_stop_loss_is_rejected(self) -> None:
        with self.assertRaises(InvalidTradeError):
            build_order_plan(
                pending_trade(side="buy", entry_price="2400", stop_loss="2400"),
                {"bid": 2397.5, "ask": 2398},
                trade_unique_id=111,
                volume=0.01,
            )

    def test_invalid_sell_stop_loss_is_rejected(self) -> None:
        with self.assertRaises(InvalidTradeError):
            build_order_plan(
                pending_trade(side="sell", entry_price="2400", stop_loss="2400"),
                {"bid": 2402, "ask": 2402.5},
                trade_unique_id=222,
                volume=0.01,
            )

    def test_invalid_trade_is_marked_without_order_submission(self) -> None:
        connection = FakeMetaApiConnection({"bid": 2397.5, "ask": 2398})

        with (
            patch.object(trade_execution, "_mark_trade_uuid_if_pending") as mark_trade,
            patch.object(trade_execution.logger, "warning"),
        ):
            result = asyncio.run(
                trade_execution._execute_pending_trades(
                    connection,
                    [pending_trade(side="buy", entry_price="2400", stop_loss="2400")],
                )
            )

        self.assertEqual(result.invalid, 1)
        self.assertEqual(result.executed, 0)
        self.assertEqual(connection.calls, [])
        mark_trade.assert_called_once_with(1, INVALID_TRADE_UUID)

    def test_metaapi_client_id_uses_required_three_part_pattern(self) -> None:
        self.assertEqual(metaapi_client_id("XAUUSD", 123), "MA_XAUUSD_123")
        self.assertLessEqual(len(metaapi_client_id("XAUUSD.PRO", 2147483647)), 31)

    def test_successful_execution_claims_trade_before_submit(self) -> None:
        connection = FakeMetaApiConnection({"bid": 2397.5, "ask": 2398})

        with (
            patch.object(trade_execution, "generate_trade_unique_id", return_value=777),
            patch.object(trade_execution, "_mark_trade_uuid_if_pending", return_value=True) as mark_trade,
        ):
            result = asyncio.run(
                trade_execution._execute_pending_trades(
                    connection,
                    [pending_trade(side="buy", entry_price="2400", stop_loss="2390")],
                )
            )

        self.assertEqual(result.executed, 1)
        self.assertEqual(result.failed, 0)
        mark_trade.assert_called_once_with(1, "777")
        self.assertEqual(connection.calls[0][1]["options"], {"magic": 777, "clientId": "MA_XAUUSD_777"})

    def test_failed_execution_releases_claim(self) -> None:
        connection = FakeMetaApiConnection({"bid": 2397.5, "ask": 2398}, fail_orders=True)

        with (
            patch.object(trade_execution, "generate_trade_unique_id", return_value=888),
            patch.object(trade_execution, "_mark_trade_uuid_if_pending", return_value=True),
            patch.object(trade_execution, "_clear_trade_uuid_if_value") as clear_trade,
            patch.object(trade_execution.logger, "exception"),
        ):
            result = asyncio.run(
                trade_execution._execute_pending_trades(
                    connection,
                    [pending_trade(side="buy", entry_price="2400", stop_loss="2390")],
                )
            )

        self.assertEqual(result.executed, 0)
        self.assertEqual(result.failed, 1)
        clear_trade.assert_called_once_with(1, "888")


def pending_trade(side: str, entry_price: str, stop_loss: str) -> PendingTrade:
    return PendingTrade(
        id=1,
        symbol="XAUUSD",
        side=side,
        entry_price=Decimal(entry_price),
        stop_loss=Decimal(stop_loss),
    )


if __name__ == "__main__":
    unittest.main()
