const messagesBody = document.querySelector("#messages-body");
const messageCount = document.querySelector("#message-count");
const emptyState = document.querySelector("#empty-state");
const statusMessage = document.querySelector("#status-message");
const syncMessagesButton = document.querySelector("#sync-messages-button");
const interpretTradesButton = document.querySelector("#interpret-trades-button");

function setStatus(message, type = "") {
    statusMessage.textContent = message;
    statusMessage.className = type ? `status ${type}` : "status";
}

function renderMessages(messages) {
    messagesBody.replaceChildren(...messages.map(createMessageRow));
    messageCount.textContent = `${messages.length} ${messages.length === 1 ? "message" : "messages"}`;
    emptyState.hidden = messages.length > 0;
}

function createMessageRow(message) {
    const row = document.createElement("tr");

    const channelCell = document.createElement("td");
    const channelName = document.createElement("span");
    channelName.className = "channel-name";
    channelName.textContent = message.channel_name;
    const channelId = document.createElement("code");
    channelId.textContent = message.channel_id;
    channelCell.append(channelName, channelId);

    const messageCell = document.createElement("td");
    const messageText = document.createElement("span");
    messageText.className = "message-text";
    messageText.textContent = message.message_text || "No text content";
    const messageTime = document.createElement("code");
    messageTime.textContent = formatDate(message.message_time);
    messageCell.append(messageText, messageTime);

    const messageIdCell = document.createElement("td");
    const messageId = document.createElement("code");
    messageId.textContent = message.message_id;
    messageIdCell.append(messageId);

    const processedCell = document.createElement("td");
    const processed = document.createElement("span");
    processed.className = `badge ${message.processed ? "success" : "muted"}`;
    processed.textContent = message.processed ? "processed" : "pending";
    processedCell.append(processed);

    row.append(channelCell, messageCell, messageIdCell, processedCell);
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

async function refreshMessages() {
    const data = await requestJson("/ops/api/messages-read");
    renderMessages(data.messages);
}

syncMessagesButton.addEventListener("click", async () => {
    syncMessagesButton.disabled = true;
    setStatus("Syncing Telegram messages...");

    try {
        const data = await requestJson("/ops/api/messages-read/sync", {method: "POST"});
        renderMessages(data.messages);

        if (data.result.skipped) {
            setStatus(data.result.detail, "error");
            return;
        }

        const statusType = data.result.failed_channels > 0 ? "error" : "success";
        setStatus(
            `Sync complete. Checked ${data.result.channels} channels, fetched ${data.result.fetched}, created ${data.result.created}, updated ${data.result.updated}, failed ${data.result.failed_channels}.`,
            statusType,
        );
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        syncMessagesButton.disabled = false;
    }
});

interpretTradesButton.addEventListener("click", async () => {
    interpretTradesButton.disabled = true;
    setStatus("Interpreting pending trade signals...");

    try {
        const data = await requestJson("/ops/api/trades/interpret", {method: "POST"});
        renderMessages(data.messages);

        if (data.result.skipped) {
            setStatus(data.result.detail, "error");
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

refreshMessages().catch((error) => setStatus(error.message, "error"));
