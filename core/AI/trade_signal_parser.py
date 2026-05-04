from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from core.AI.trade_signal_prompt import TRADE_SIGNAL_SYSTEM_PROMPT

NUMBER_RE = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
NUMBER_TOKEN_RE = re.compile(rf"(?<![A-Z0-9])(?P<number>{NUMBER_RE})(?![A-Z0-9])")

GOLD_PATTERNS = [
    r"\bGOLD\b",
    r"\bXAU\b",
    r"\bXAUUSD\b",
    r"\bXAU\s+USD\b",
    r"\bGOLDUSD\b",
    r"\bGOLD\s+USD\b",
    r"\bGOLD\s+SPOT\b",
    r"\bSPOT\s+GOLD\b",
]

UNSUPPORTED_SYMBOL_PATTERNS = [
    r"\bBTC\b",
    r"\bBTCUSD\b",
    r"\bBTC\s+USD\b",
    r"\bBTCUSDT\b",
    r"\bBTC\s+USDT\b",
    r"\bETH\b",
    r"\bETHUSD\b",
    r"\bETH\s+USD\b",
    r"\bETHUSDT\b",
    r"\bETH\s+USDT\b",
    r"\bSOL\b",
    r"\bSOLUSD\b",
    r"\bSOLUSDT\b",
    r"\bBNB\b",
    r"\bBNBUSD\b",
    r"\bBNBUSDT\b",
    r"\bXRP\b",
    r"\bXRPUSD\b",
    r"\bXRPUSDT\b",
    r"\bEURUSD\b",
    r"\bEUR\s+USD\b",
    r"\bGBPUSD\b",
    r"\bGBP\s+USD\b",
    r"\bUSDJPY\b",
    r"\bUSD\s+JPY\b",
    r"\bAUDUSD\b",
    r"\bAUD\s+USD\b",
    r"\bNZDUSD\b",
    r"\bNZD\s+USD\b",
    r"\bUSDCAD\b",
    r"\bUSD\s+CAD\b",
    r"\bUSDCHF\b",
    r"\bUSD\s+CHF\b",
    r"\bEURJPY\b",
    r"\bEUR\s+JPY\b",
    r"\bGBPJPY\b",
    r"\bGBP\s+JPY\b",
    r"\bNAS100\b",
    r"\bNASDAQ\b",
    r"\bUS100\b",
    r"\bUS30\b",
    r"\bDOW\b",
    r"\bDJIA\b",
    r"\bSPX\b",
    r"\bSP500\b",
    r"\bS\s*P\s*500\b",
    r"\bGER40\b",
    r"\bDAX\b",
    r"\bSILVER\b",
    r"\bXAG\b",
    r"\bXAGUSD\b",
    r"\bXAG\s+USD\b",
    r"\bOIL\b",
    r"\bUSOIL\b",
    r"\bUS\s+OIL\b",
    r"\bUKOIL\b",
    r"\bUK\s+OIL\b",
    r"\bWTI\b",
    r"\bCRUDE\b",
    r"\bBRENT\b",
]

BUY_PATTERNS = [
    r"\bBUY\b",
    r"\bLONG\b",
    r"\bBULLISH\b",
    r"\bGO\s+LONG\b",
]

SELL_PATTERNS = [
    r"\bSELL\b",
    r"\bSHORT\b",
    r"\bBEARISH\b",
    r"\bGO\s+SHORT\b",
]

NEGATIVE_STOP_LOSS_PATTERNS = [
    r"\bNO\s+SL\b",
    r"\bNO\s+STOP\s+LOSS\b",
    r"\bWITHOUT\s+SL\b",
    r"\bWITHOUT\s+STOP\s+LOSS\b",
    r"\bSL\s+LATER\b",
    r"\bSTOP\s+LOSS\s+LATER\b",
    r"\bSL\s+WILL\s+UPDATE\b",
    r"\bSTOP\s+LOSS\s+WILL\s+UPDATE\b",
    r"\bSL\s+TO\s+BE\s+UPDATED\b",
    r"\bSTOP\s+LOSS\s+TO\s+BE\s+UPDATED\b",
    r"\bSL\s+OPEN\b",
    r"\bSTOP\s+LOSS\s+OPEN\b",
    r"\bSL\s+SOON\b",
    r"\bSTOP\s+LOSS\s+SOON\b",
    r"\bSL\s+MANUAL\b",
    r"\bSTOP\s+LOSS\s+MANUAL\b",
]

ENTRY_LABEL_RE = re.compile(
    r"\b(?:ENTRY\s+PRICE|ENTRYPRICE|ENTRIES|ENTRY|EP|OPEN\s+PRICE|OPENING\s+PRICE)\b"
)
ENTRY_SECTION_END_RE = re.compile(
    r"\b(?:SL|STP|STOP|STOP\s+LOSS|TP\d*|TAKE\s+PROFIT|TARGET\d*|TGT\d*|LOT|LOTS|RISK)\b"
)
TRADE_PARAMETER_RE = re.compile(
    r"\b(?:SL|STP|STOP|STOP\s+LOSS|TP\d*|TAKE\s+PROFIT|TARGET\d*|TGT\d*)\b"
)
NON_ENTRY_NUMBER_CONTEXT = {"LOT", "LOTS", "RISK", "RR", "LEVERAGE"}


@dataclass(frozen=True)
class ExpectedValidTrade:
    symbol: str
    side: str
    entry_price_json: int | float
    entry_price_decimal: Decimal
    stop_loss_json: int | float
    stop_loss_decimal: Decimal


@dataclass(frozen=True)
class SignalExpectation:
    error_message: str | None
    valid_trades: list[ExpectedValidTrade] | None


class TradeSignalValidationError(Exception):
    pass


class LLMRequestError(Exception):
    pass


def parse_trade_signal_with_llm(
    raw_signal: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    reasoning_effort: str | None,
    temperature: float,
    max_tokens: int,
    retries: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not raw_signal or not raw_signal.strip():
        return {"error": True, "message": "invalid signal"}

    last_validation_error: str | None = None

    for attempt in range(retries + 1):
        try:
            raw_model_output = _call_openai_compatible_llm(
                raw_signal,
                api_key=api_key,
                base_url=base_url,
                model=model,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                validation_error=last_validation_error if attempt > 0 else None,
            )
            parsed = extract_json_object(raw_model_output)
            return validate_model_json(parsed, raw_signal)
        except TradeSignalValidationError as exc:
            last_validation_error = str(exc)

    local_expectation = expected_from_signal(raw_signal)
    if local_expectation.error_message is None and local_expectation.valid_trades is not None:
        return success_response_from_expected_trades(local_expectation.valid_trades)

    return {
        "error": True,
        "message": f"llm output validation failed: {last_validation_error}",
    }


def _call_openai_compatible_llm(
    raw_signal: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    reasoning_effort: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    validation_error: str | None,
) -> str:
    user_content = f"Parse this trade signal:\n{raw_signal}"
    if validation_error:
        user_content = (
            "Your previous JSON failed local validation.\n"
            f"Validation error: {validation_error}\n\n"
            "Return corrected JSON only for this same trade signal:\n"
            f"{raw_signal}"
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": TRADE_SIGNAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMRequestError(f"LLM request failed: {exc.code} {detail}") from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        raise LLMRequestError(f"LLM request failed: {exc}") from exc

    try:
        parsed_response = json.loads(response_body)
        content = parsed_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMRequestError("LLM response did not match chat completions format") from exc

    if not content:
        raise TradeSignalValidationError("empty model response")

    return str(content)


def validate_model_json(model_json: dict[str, Any], raw_signal: str) -> dict[str, Any]:
    expectation = expected_from_signal(raw_signal)

    if expectation.error_message is not None:
        return {"error": True, "message": expectation.error_message}

    expected_trades = expectation.valid_trades
    if expected_trades is None:
        raise TradeSignalValidationError("internal validation error: expected trades missing")

    require_exact_keys(model_json, {"error", "trades"}, "success output")

    if model_json["error"] is not False:
        raise TradeSignalValidationError("model returned error=true for a valid signal")

    trades = model_json["trades"]
    if not isinstance(trades, list):
        raise TradeSignalValidationError("trades must be a list")

    if len(trades) != len(expected_trades):
        raise TradeSignalValidationError(f"trades must contain {len(expected_trades)} trade(s)")

    for index, (trade, expected_trade) in enumerate(zip(trades, expected_trades), start=1):
        if not isinstance(trade, dict):
            raise TradeSignalValidationError(f"trades[{index}] must be an object")

        require_exact_keys(trade, {"symbol", "side", "entry_price", "stop_loss"}, f"trades[{index}]")

        if trade["symbol"] != expected_trade.symbol:
            raise TradeSignalValidationError(f"trades[{index}].symbol must be {expected_trade.symbol}")

        if trade["side"] != expected_trade.side:
            raise TradeSignalValidationError(f"trades[{index}].side must be {expected_trade.side}")

        if not is_json_number(trade["entry_price"]):
            raise TradeSignalValidationError(f"trades[{index}].entry_price must be a JSON number")

        actual_entry_price_decimal = Decimal(str(trade["entry_price"]))
        if actual_entry_price_decimal != expected_trade.entry_price_decimal:
            raise TradeSignalValidationError(
                f"trades[{index}].entry_price must equal entry value {expected_trade.entry_price_json}"
            )

        if not is_json_number(trade["stop_loss"]):
            raise TradeSignalValidationError(f"trades[{index}].stop_loss must be a JSON number")

        actual_stop_loss_decimal = Decimal(str(trade["stop_loss"]))
        if actual_stop_loss_decimal != expected_trade.stop_loss_decimal:
            raise TradeSignalValidationError(
                f"trades[{index}].stop_loss must equal explicitly labelled SL value {expected_trade.stop_loss_json}"
            )

    return success_response_from_expected_trades(expected_trades)


def success_response_from_expected_trades(expected_trades: list[ExpectedValidTrade]) -> dict[str, Any]:
    return {
        "error": False,
        "trades": [
            {
                "symbol": expected_trade.symbol,
                "side": expected_trade.side,
                "entry_price": expected_trade.entry_price_json,
                "stop_loss": expected_trade.stop_loss_json,
            }
            for expected_trade in expected_trades
        ],
    }


def expected_from_signal(raw_signal: str) -> SignalExpectation:
    text = normalize_text(raw_signal)

    has_gold = has_any_pattern(text, GOLD_PATTERNS)
    has_unsupported = has_any_pattern(text, UNSUPPORTED_SYMBOL_PATTERNS)

    if has_gold and has_unsupported:
        return SignalExpectation("ambiguous symbol", None)

    if not has_gold:
        if has_unsupported:
            return SignalExpectation("only gold signals are supported", None)
        return SignalExpectation("symbol not found", None)

    has_buy = has_any_pattern(text, BUY_PATTERNS)
    has_sell = has_any_pattern(text, SELL_PATTERNS)

    if not has_buy and not has_sell:
        return SignalExpectation("side not found", None)

    if has_buy and has_sell:
        return SignalExpectation("ambiguous side", None)

    side = "buy" if has_buy else "sell"

    entry_values = extract_entry_values(text, side)
    if not entry_values:
        return SignalExpectation("entry price not found", None)

    if len(entry_values) > 2:
        return SignalExpectation("ambiguous entry price", None)

    if has_any_pattern(text, NEGATIVE_STOP_LOSS_PATTERNS):
        return SignalExpectation("stop loss not found", None)

    stop_pattern = re.compile(
        rf"(?<![A-Z])(?P<label>STOP\s+LOSS|SL|STP|STOP)\s*(?P<number>{NUMBER_RE})"
    )

    found_values: list[tuple[int | float, Decimal]] = []
    for match in stop_pattern.finditer(text):
        label = match.group("label")
        if label == "STOP" and previous_token(text, match.start()) in {"BUY", "SELL"}:
            continue

        try:
            found_values.append(parse_number(match.group("number")))
        except TradeSignalValidationError:
            continue

    if not found_values:
        return SignalExpectation("stop loss not found", None)

    unique_decimals = {decimal_value for _, decimal_value in found_values}
    if len(unique_decimals) > 1:
        return SignalExpectation("ambiguous stop loss", None)

    stop_loss_json, stop_loss_decimal = found_values[0]
    return SignalExpectation(
        None,
        [
            ExpectedValidTrade(
                symbol="XAUUSD",
                side=side,
                entry_price_json=entry_price_json,
                entry_price_decimal=entry_price_decimal,
                stop_loss_json=stop_loss_json,
                stop_loss_decimal=stop_loss_decimal,
            )
            for entry_price_json, entry_price_decimal in entry_values
        ],
    )


def extract_entry_values(text: str, side: str) -> list[tuple[int | float, Decimal]]:
    labelled_values = extract_labelled_entry_values(text)
    if labelled_values:
        return unique_price_values(labelled_values)

    side_match = first_side_match(text, side)
    if side_match is None:
        return []

    segment_end = next_trade_parameter_start(text, side_match.end())
    return unique_price_values(extract_price_values(text[side_match.end() : segment_end]))


def extract_labelled_entry_values(text: str) -> list[tuple[int | float, Decimal]]:
    values: list[tuple[int | float, Decimal]] = []
    for match in ENTRY_LABEL_RE.finditer(text):
        segment_end = next_match_start(ENTRY_SECTION_END_RE, text, match.end())
        values.extend(extract_price_values(text[match.end() : segment_end]))
    return values


def first_side_match(text: str, side: str) -> re.Match[str] | None:
    patterns = BUY_PATTERNS if side == "buy" else SELL_PATTERNS
    matches = [match for pattern in patterns if (match := re.search(pattern, text))]
    if not matches:
        return None
    return min(matches, key=lambda match: match.start())


def next_match_start(pattern: re.Pattern[str], text: str, start: int) -> int:
    match = pattern.search(text, start)
    return match.start() if match else len(text)


def next_trade_parameter_start(text: str, start: int) -> int:
    search_start = start
    while match := TRADE_PARAMETER_RE.search(text, search_start):
        if match.group(0) == "STOP" and previous_token(text, match.start()) in {"BUY", "SELL"}:
            search_start = match.end()
            continue

        return match.start()

    return len(text)


def extract_price_values(text: str) -> list[tuple[int | float, Decimal]]:
    values: list[tuple[int | float, Decimal]] = []
    for match in NUMBER_TOKEN_RE.finditer(text):
        if is_non_entry_number_context(text, match.start(), match.end()):
            continue

        try:
            values.append(parse_number(match.group("number")))
        except TradeSignalValidationError:
            continue
    return values


def unique_price_values(values: list[tuple[int | float, Decimal]]) -> list[tuple[int | float, Decimal]]:
    unique_values: list[tuple[int | float, Decimal]] = []
    seen: set[Decimal] = set()
    for json_value, decimal_value in values:
        if decimal_value in seen:
            continue
        seen.add(decimal_value)
        unique_values.append((json_value, decimal_value))
    return unique_values


def is_non_entry_number_context(text: str, start: int, end: int) -> bool:
    before = previous_token(text, start)
    after = next_token(text, end)
    return before in NON_ENTRY_NUMBER_CONTEXT or after in NON_ENTRY_NUMBER_CONTEXT


def extract_json_object(content: str) -> dict[str, Any]:
    content = content.strip()

    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise TradeSignalValidationError("model output JSON must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content)

    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise TradeSignalValidationError("model output JSON must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    if start == -1:
        raise TradeSignalValidationError("model did not return JSON")

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(content)):
        char = content[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = content[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise TradeSignalValidationError("model returned invalid JSON") from exc
                if not isinstance(parsed, dict):
                    raise TradeSignalValidationError("model output JSON must be an object")
                return parsed

    raise TradeSignalValidationError("model returned incomplete JSON")


def normalize_text(text: str) -> str:
    normalized = str(text or "").upper()
    normalized = re.sub(r"\bXAU\s*[/\-_]\s*USD\b", " XAU USD ", normalized)
    normalized = re.sub(r"\bGOLD\s*[/\-_]\s*USD\b", " GOLD USD ", normalized)
    normalized = re.sub(r"\bXAG\s*[/\-_]\s*USD\b", " XAG USD ", normalized)
    normalized = re.sub(r"\bS\s*[\/\.\-_]\s*L\b", " SL ", normalized)
    normalized = re.sub(r"\bSTOP\s*[-_]\s*LOSS\b", " STOP LOSS ", normalized)
    normalized = re.sub(r"\bSTOPLOSS\b", " STOP LOSS ", normalized)
    normalized = re.sub(r"\bT\s*[\/\.\-_]\s*P\b", " TP ", normalized)
    normalized = re.sub(r"\bTAKE\s*[-_]\s*PROFIT\b", " TAKE PROFIT ", normalized)
    normalized = re.sub(r"\bTAKEPROFIT\b", " TAKE PROFIT ", normalized)
    normalized = normalized.replace("#", " ")
    normalized = re.sub(r"(?<!\d)\.(?!\d)", " ", normalized)
    normalized = re.sub(r"(?<!\d),(?!\d)", " ", normalized)
    normalized = re.sub(r"[/\\:;=@|()\[\]{}<>\"'`~!?\*\n\r\t_+\-]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def parse_number(raw_number: str) -> tuple[int | float, Decimal]:
    cleaned = raw_number.replace(",", "")

    try:
        decimal_value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise TradeSignalValidationError(f"invalid numeric value: {raw_number}") from exc

    if decimal_value <= 0:
        raise TradeSignalValidationError(f"invalid non-positive price: {raw_number}")

    if "." in cleaned:
        return float(cleaned), decimal_value

    return int(cleaned), decimal_value


def previous_token(text: str, char_index: int) -> str | None:
    before = text[:char_index].strip()
    if not before:
        return None

    tokens = before.split()
    return tokens[-1] if tokens else None


def next_token(text: str, char_index: int) -> str | None:
    after = text[char_index:].strip()
    if not after:
        return None

    tokens = after.split()
    return tokens[0] if tokens else None


def has_any_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def require_exact_keys(obj: dict[str, Any], expected_keys: set[str], where: str) -> None:
    actual_keys = set(obj.keys())
    if actual_keys != expected_keys:
        raise TradeSignalValidationError(
            f"{where} must contain exactly keys {sorted(expected_keys)}, got {sorted(actual_keys)}"
        )


def is_json_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
