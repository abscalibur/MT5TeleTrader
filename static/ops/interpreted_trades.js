const tradesBody = document.querySelector("#trades-body");
const tradeCount = document.querySelector("#trade-count");
const emptyState = document.querySelector("#empty-state");
const statusMessage = document.querySelector("#status-message");
const interpretTradesButton = document.querySelector("#interpret-trades-button");
const tradeInterpretationJobId = "interpret_trades_from_messages";

function setStatus(message, type = "") {
    statusMessage.textContent = message;
    statusMessage.className = type ? `status ${type}` : "status";
}

function renderTrades(trades) {
    tradesBody.replaceChildren(...trades.map(createTradeRow));
    tradeCount.textContent = `${trades.length} ${trades.length === 1 ? "trade" : "trades"}`;
    emptyState.hidden = trades.length > 0;
}

function createElement(tagName, className, textContent) {
    const element = document.createElement(tagName);
    if (className) {
        element.className = className;
    }
    element.textContent = textContent;
    return element;
}

function createCell(...children) {
    const cell = document.createElement("td");
    cell.append(...children);
    return cell;
}

function createTradeRow(trade) {
    const row = document.createElement("tr");
    const tradeUuid = trade.trade_uuid || "n/a";

    row.append(
        createCell(
            createElement("span", "channel-name", trade.channel_name),
            createElement("code", "", trade.channel_id),
        ),
        createCell(
            createElement("span", "trade-symbol", trade.symbol),
            createElement("span", "badge muted", trade.side),
            createElement("code", "", `uuid ${tradeUuid}`),
        ),
        createCell(createElement("code", "", trade.entry_price || "n/a")),
        createCell(createElement("code", "", trade.stoploss)),
        createCell(
            createElement("span", "message-text", trade.message_text || "No text content"),
            createElement("code", "", `${formatDate(trade.message_time)} - message ${trade.message_id}`),
        ),
    );

    return row;
}

function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return date.toLocaleString();
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {"Content-Type": "application/json", ...(options.headers || {})},
        ...options,
    });
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Request failed");
    }

    return data;
}

async function refreshTrades() {
    const data = await requestJson("/ops/api/interpreted-trades");
    renderTrades(data.trades);
}

interpretTradesButton.addEventListener("click", async () => {
    interpretTradesButton.disabled = true;
    setStatus("Interpreting pending trade signals...");

    try {
        const data = await requestJson(`/ops/api/jobs/${encodeURIComponent(tradeInterpretationJobId)}/run`, {
            method: "POST",
        });
        await refreshTrades();

        if (data.result.skipped) {
            setStatus(data.result.detail, "warning");
            return;
        }

        const statusType = data.result.failed > 0 ? "error" : "success";
        setStatus(
            `Interpretation complete. Found ${data.result.fetched}, processed ${data.result.processed}, created ${data.result.created}, updated ${data.result.updated}, invalid ${data.result.invalid}, failed ${data.result.failed}.`,
            statusType,
        );
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        interpretTradesButton.disabled = false;
    }
});

refreshTrades().catch((error) => setStatus(error.message, "error"));
