import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ops.channels import run_channel_sync_job
from ops.messages import run_message_sync_job
from ops.trade_execution import run_trade_execution_job
from ops.trades import run_trade_interpretation_job
from settings import settings

CHANNEL_SYNC_JOB_ID = "sync_telegram_channels"
MESSAGE_SYNC_JOB_ID = "sync_telegram_messages"
TRADE_INTERPRETATION_JOB_ID = "interpret_trades_from_messages"
TRADE_EXECUTION_JOB_ID = "execute_pending_trades"

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


@dataclass(frozen=True)
class ScheduledJobDefinition:
    id: str
    name: str
    interval_minutes: int
    runner: Callable[[], Awaitable[Any]]


JOB_DEFINITIONS = {
    CHANNEL_SYNC_JOB_ID: ScheduledJobDefinition(
        id=CHANNEL_SYNC_JOB_ID,
        name="Sync Telegram channels",
        interval_minutes=settings.CHANNEL_SYNC_INTERVAL_MINUTES,
        runner=run_channel_sync_job,
    ),
    MESSAGE_SYNC_JOB_ID: ScheduledJobDefinition(
        id=MESSAGE_SYNC_JOB_ID,
        name="Sync Telegram messages",
        interval_minutes=settings.MESSAGE_SYNC_INTERVAL_MINUTES,
        runner=run_message_sync_job,
    ),
    TRADE_INTERPRETATION_JOB_ID: ScheduledJobDefinition(
        id=TRADE_INTERPRETATION_JOB_ID,
        name="Interpret trades from MessageRead rows",
        interval_minutes=settings.TRADE_INTERPRETATION_INTERVAL_MINUTES,
        runner=run_trade_interpretation_job,
    ),
    TRADE_EXECUTION_JOB_ID: ScheduledJobDefinition(
        id=TRADE_EXECUTION_JOB_ID,
        name="Execute pending interpreted trades",
        interval_minutes=settings.TRADE_EXECUTION_INTERVAL_MINUTES,
        runner=run_trade_execution_job,
    ),
}

_job_state: dict[str, dict[str, Any]] = {
    job_id: {
        "running": False,
        "last_status": "never_run",
        "last_run_at": None,
        "last_finished_at": None,
        "last_result": None,
        "last_error": "",
        "run_count": 0,
        "failure_count": 0,
    }
    for job_id in JOB_DEFINITIONS
}


def start_scheduler() -> None:
    if scheduler.running:
        logger.debug("Scheduler already running")
        return

    for definition in JOB_DEFINITIONS.values():
        scheduler.add_job(
            run_scheduler_job,
            args=[definition.id],
            trigger=IntervalTrigger(minutes=definition.interval_minutes),
            id=definition.id,
            name=definition.name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    scheduler.start()
    for definition in JOB_DEFINITIONS.values():
        logger.info(
            "Scheduler started: job_id=%s interval_minutes=%s",
            definition.id,
            definition.interval_minutes,
        )


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info(
            "Scheduler stopped: job_ids=%s",
            ",".join(JOB_DEFINITIONS),
        )


async def run_scheduler_job(job_id: str) -> dict[str, Any]:
    definition = JOB_DEFINITIONS.get(job_id)
    if definition is None:
        raise ValueError(f"Unknown scheduler job: {job_id}")

    started_at = _utc_now_iso()
    state = _job_state[job_id]
    state.update(
        {
            "running": True,
            "last_status": "running",
            "last_run_at": started_at,
            "last_finished_at": None,
            "last_error": "",
            "run_count": int(state["run_count"]) + 1,
        }
    )

    try:
        result = await definition.runner()
        result_data = _serialize_result(result)
        status = "skipped" if result_data.get("skipped") else "success"
        state.update(
            {
                "running": False,
                "last_status": status,
                "last_finished_at": _utc_now_iso(),
                "last_result": result_data,
            }
        )
        return {"job": serialize_scheduler_job(job_id), "result": result_data}
    except Exception as exc:
        state.update(
            {
                "running": False,
                "last_status": "failed",
                "last_finished_at": _utc_now_iso(),
                "last_error": str(exc),
                "failure_count": int(state["failure_count"]) + 1,
            }
        )
        raise


def list_scheduler_jobs() -> list[dict[str, Any]]:
    return [serialize_scheduler_job(job_id) for job_id in JOB_DEFINITIONS]


def serialize_scheduler_job(job_id: str) -> dict[str, Any]:
    definition = JOB_DEFINITIONS[job_id]
    scheduled_job = scheduler.get_job(job_id)
    state = _job_state[job_id]

    return {
        "id": definition.id,
        "name": definition.name,
        "interval_minutes": definition.interval_minutes,
        "trigger": str(scheduled_job.trigger) if scheduled_job else "interval",
        "next_run_time": _datetime_iso(getattr(scheduled_job, "next_run_time", None)),
        "scheduler_running": scheduler.running,
        "running": state["running"],
        "last_status": state["last_status"],
        "last_run_at": state["last_run_at"],
        "last_finished_at": state["last_finished_at"],
        "last_result": state["last_result"],
        "last_error": state["last_error"],
        "run_count": state["run_count"],
        "failure_count": state["failure_count"],
    }


def _serialize_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, dict):
        return result
    return {"detail": str(result)}


def _datetime_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
