const channelsBody = document.querySelector("#channels-body");
const channelCount = document.querySelector("#channel-count");
const emptyState = document.querySelector("#empty-state");
const statusMessage = document.querySelector("#status-message");
const syncButton = document.querySelector("#sync-button");

function setStatus(message, type = "") {
    statusMessage.textContent = message;
    statusMessage.className = type ? `status ${type}` : "status";
}

function renderChannels(channels) {
    channelsBody.replaceChildren(...channels.map(createChannelRow));
    channelCount.textContent = `${channels.length} ${channels.length === 1 ? "channel" : "channels"}`;
    emptyState.hidden = channels.length > 0;
}

function createChannelRow(channel) {
    const row = document.createElement("tr");
    row.dataset.channelId = channel.id;

    const channelCell = document.createElement("td");
    const name = document.createElement("span");
    name.className = "channel-name";
    name.textContent = channel.name;
    const id = document.createElement("code");
    id.textContent = channel.id;
    channelCell.append(name, id);

    const enabledCell = document.createElement("td");
    const label = document.createElement("label");
    label.className = "switch";
    const input = document.createElement("input");
    input.className = "channel-toggle";
    input.type = "checkbox";
    input.checked = channel.enabled;
    const slider = document.createElement("span");
    slider.textContent = `Toggle ${channel.name}`;
    label.append(input, slider);
    enabledCell.append(label);

    row.append(channelCell, enabledCell);
    return row;
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

async function refreshChannels() {
    const data = await requestJson("/ops/api/channels");
    renderChannels(data.channels);
}

async function updateChannel(row, toggle) {
    const enabled = toggle.checked;
    toggle.disabled = true;

    try {
        await requestJson(`/ops/api/channels/${encodeURIComponent(row.dataset.channelId)}`, {
            method: "PATCH",
            body: JSON.stringify({enabled}),
        });
        setStatus("Channel updated.", "success");
    } catch (error) {
        toggle.checked = !enabled;
        setStatus(error.message, "error");
    } finally {
        toggle.disabled = false;
    }
}

channelsBody.addEventListener("change", (event) => {
    if (!event.target.matches(".channel-toggle")) {
        return;
    }

    updateChannel(event.target.closest("tr"), event.target);
});

syncButton.addEventListener("click", async () => {
    syncButton.disabled = true;
    setStatus("Syncing Telegram channels...");

    try {
        const data = await requestJson("/ops/api/channels/sync", {method: "POST"});
        renderChannels(data.channels);

        if (data.result.skipped) {
            setStatus(data.result.detail, "error");
            return;
        }

        setStatus(
            `Sync complete. Fetched ${data.result.fetched}, created ${data.result.created}, updated ${data.result.updated}.`,
            "success",
        );
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        syncButton.disabled = false;
    }
});

refreshChannels().catch((error) => setStatus(error.message, "error"));
