import unittest
from unittest.mock import patch

from core.AI.trade_signal_parser import (
    TradeSignalValidationError,
    parse_trade_signal_with_llm,
    validate_model_json,
)


LAYERED_SELL_SIGNAL = (
    " Sell Gold @4568.7-4578.7 Sl :4582.7 Tp1:4564.7 Tp2:4560 "
    "Enter Slowly-Layer with proper money management Do not rush your entries "
)


class TradeSignalParserTests(unittest.TestCase):
    def test_valid_signal_returns_one_trade_with_entry_price(self) -> None:
        parsed = validate_model_json(
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "buy",
                        "entry_price": 2350,
                        "stop_loss": 2340,
                    }
                ],
            },
            "GOLD BUY 2350 SL 2340",
        )

        self.assertEqual(
            parsed,
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "buy",
                        "entry_price": 2350,
                        "stop_loss": 2340,
                    }
                ],
            },
        )

    def test_valid_signal_returns_two_trades_for_two_entry_prices(self) -> None:
        parsed = validate_model_json(
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "sell",
                        "entry_price": 2350,
                        "stop_loss": 2365,
                    },
                    {
                        "symbol": "XAUUSD",
                        "side": "sell",
                        "entry_price": 2355,
                        "stop_loss": 2365,
                    },
                ],
            },
            "XAUUSD SELL ENTRY 2350 - 2355 SL 2365",
        )

        self.assertEqual(len(parsed["trades"]), 2)
        self.assertEqual([trade["entry_price"] for trade in parsed["trades"]], [2350, 2355])

    def test_at_price_range_signal_returns_two_trades(self) -> None:
        parsed = validate_model_json(
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "sell",
                        "entry_price": 4568.7,
                        "stop_loss": 4582.7,
                    },
                    {
                        "symbol": "XAUUSD",
                        "side": "sell",
                        "entry_price": 4578.7,
                        "stop_loss": 4582.7,
                    },
                ],
            },
            LAYERED_SELL_SIGNAL,
        )

        self.assertEqual(
            parsed["trades"],
            [
                {
                    "symbol": "XAUUSD",
                    "side": "sell",
                    "entry_price": 4568.7,
                    "stop_loss": 4582.7,
                },
                {
                    "symbol": "XAUUSD",
                    "side": "sell",
                    "entry_price": 4578.7,
                    "stop_loss": 4582.7,
                },
            ],
        )

    def test_llm_rejection_falls_back_to_local_valid_parse(self) -> None:
        with patch(
            "core.AI.trade_signal_parser._call_openai_compatible_llm",
            return_value='{"error": true, "message": "entry price not found"}',
        ):
            parsed = parse_trade_signal_with_llm(
                LAYERED_SELL_SIGNAL,
                api_key="test-key",
                base_url="https://example.invalid/v1",
                model="test-model",
                reasoning_effort=None,
                temperature=0,
                max_tokens=500,
                retries=0,
                timeout_seconds=1,
            )

        self.assertFalse(parsed["error"])
        self.assertEqual([trade["entry_price"] for trade in parsed["trades"]], [4568.7, 4578.7])

    def test_missing_entry_price_is_invalid(self) -> None:
        parsed = validate_model_json(
            {
                "error": True,
                "message": "entry price not found",
            },
            "GOLD BUY SL 2340",
        )

        self.assertEqual(parsed, {"error": True, "message": "entry price not found"})

    def test_take_profit_price_is_not_treated_as_entry(self) -> None:
        parsed = validate_model_json(
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "buy",
                        "entry_price": 2350,
                        "stop_loss": 2340,
                    }
                ],
            },
            "GOLD BUY 2350 TP1 2360 SL 2340",
        )

        self.assertEqual(len(parsed["trades"]), 1)
        self.assertEqual(parsed["trades"][0]["entry_price"], 2350)

    def test_buy_stop_order_price_is_treated_as_entry(self) -> None:
        parsed = validate_model_json(
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "buy",
                        "entry_price": 2350,
                        "stop_loss": 2340,
                    }
                ],
            },
            "GOLD BUY STOP 2350 SL 2340",
        )

        self.assertEqual(parsed["trades"][0]["entry_price"], 2350)

    def test_signal_with_link_is_rejected(self) -> None:
        parsed = validate_model_json(
            {
                "error": False,
                "trades": [
                    {
                        "symbol": "XAUUSD",
                        "side": "buy",
                        "entry_price": 4543,
                        "stop_loss": 4523,
                    }
                ],
            },
            "XAUUSD BUY 4543 TP 4546 SL 4523 VIP GROUP JOIN FAST https://t.me/+NAIP137_tt8wOTBk",
        )

        self.assertEqual(parsed, {"error": True, "message": "links are not allowed"})

    def test_signal_with_link_skips_llm_call(self) -> None:
        with patch("core.AI.trade_signal_parser._call_openai_compatible_llm") as llm_call:
            parsed = parse_trade_signal_with_llm(
                "XAUUSD BUY 4543 TP 4546 SL 4523 https://t.me/+NAIP137_tt8wOTBk",
                api_key="test-key",
                base_url="https://example.invalid/v1",
                model="test-model",
                reasoning_effort=None,
                temperature=0,
                max_tokens=500,
                retries=0,
                timeout_seconds=1,
            )

        self.assertEqual(parsed, {"error": True, "message": "links are not allowed"})
        llm_call.assert_not_called()

    def test_success_payload_must_use_trades_list(self) -> None:
        with self.assertRaises(TradeSignalValidationError):
            validate_model_json(
                {
                    "error": False,
                    "trade": {
                        "symbol": "XAUUSD",
                        "side": "buy",
                        "entry_price": 2350,
                        "stop_loss": 2340,
                    },
                },
                "GOLD BUY 2350 SL 2340",
            )


if __name__ == "__main__":
    unittest.main()
