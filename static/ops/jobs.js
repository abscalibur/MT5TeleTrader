const jobsBody = document.querySelector("#jobs-body");
const jobCount = document.querySelector("#job-count");
const emptyState = document.querySelector("#empty-state");
const statusMessage = document.querySelector("#status-message");
const refreshJobsButton = document.querySelector("#refresh-jobs-button");

function setStatus(message, type = "") {
    statusMessage.textContent = message;
    statusMessage.className = type ? `status ${type}` : "status";
}

function renderJobs(jobs) {
    jobsBody.replaceChildren(...jobs.map(createJobRow));
    jobCount.textContent = `${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}`;
    emptyState.hidden = jobs.length > 0;
}

function createJobRow(job) {
    const row = document.createElement("tr");
    row.dataset.jobId = job.id;

    const jobCell = document.createElement("td");
    const jobName = document.createElement("span");
    jobName.className = "channel-name";
    jobName.textContent = job.name;
    const jobId = document.createElement("code");
    jobId.textContent = job.id;
    jobCell.append(jobName, jobId);

    const scheduleCell = document.createElement("td");
    const interval = document.createElement("span");
    interval.className = "channel-name";
    interval.textContent = `Every ${job.interval_minutes} minutes`;
    const nextRun = document.createElement("code");
    nextRun.textContent = job.next_run_time ? `Next ${formatDate(job.next_run_time)}` : "Not scheduled";
    scheduleCell.append(interval, nextRun);

    const lastRunCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `badge ${statusClass(job.last_status)}`;
    status.textContent = job.running ? "running" : job.last_status;
    const lastRun = document.createElement("code");
    lastRun.textContent = job.last_run_at ? formatDate(job.last_run_at) : "Never";
    lastRunCell.append(status, lastRun);

    const resultCell = document.createElement("td");
    const result = document.createElement("span");
    result.className = "job-result";
    result.textContent = job.last_error || formatResult(job.last_result);
    resultCell.append(result);

    const actionCell = document.createElement("td");
    const runButton = document.createElement("button");
    runButton.className = "secondary-button run-job-button";
    runButton.type = "button";
    runButton.disabled = job.running;
    runButton.textContent = job.running ? "Running..." : "Run Now";
    actionCell.append(runButton);

    row.append(jobCell, scheduleCell, lastRunCell, resultCell, actionCell);
    return row;
}

function statusClass(status) {
    if (status === "success") {
        return "success";
    }
    if (status === "failed") {
        return "error";
    }
    if (status === "running" || status === "skipped") {
        return "warning";
    }
    return "muted";
}

function formatResult(result) {
    if (!result) {
        return "No result yet";
    }

    return Object.entries(result)
        .filter(([, value]) => value !== "" && value !== false && value !== null)
        .map(([key, value]) => `${key}: ${value}`)
        .join(", ");
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

async function refreshJobs() {
    const data = await requestJson("/ops/api/jobs");
    renderJobs(data.jobs);
}

jobsBody.addEventListener("click", async (event) => {
    if (!event.target.matches(".run-job-button")) {
        return;
    }

    const row = event.target.closest("tr");
    const jobId = row.dataset.jobId;
    event.target.disabled = true;
    setStatus(`Running ${jobId}...`);

    try {
        const data = await requestJson(`/ops/api/jobs/${encodeURIComponent(jobId)}/run`, {method: "POST"});
        renderJobs(data.jobs);

        if (data.result.skipped) {
            setStatus(data.result.detail, "warning");
            return;
        }

        setStatus(`${data.job.name} completed.`, "success");
    } catch (error) {
        setStatus(error.message, "error");
        refreshJobs().catch(() => undefined);
    }
});

refreshJobsButton.addEventListener("click", async () => {
    refreshJobsButton.disabled = true;
    setStatus("Refreshing scheduled jobs...");

    try {
        await refreshJobs();
        setStatus("Scheduled jobs refreshed.", "success");
    } catch (error) {
        setStatus(error.message, "error");
    } finally {
        refreshJobsButton.disabled = false;
    }
});

refreshJobs().catch((error) => setStatus(error.message, "error"));
