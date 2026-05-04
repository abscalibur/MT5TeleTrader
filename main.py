from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.logging_config import configure_logging
from ops.channels import list_channels, set_channel_enabled
from ops.messages import list_messages_read
from ops.scheduler import (
    CHANNEL_SYNC_JOB_ID,
    MESSAGE_SYNC_JOB_ID,
    TRADE_INTERPRETATION_JOB_ID,
    list_scheduler_jobs,
    run_scheduler_job,
    start_scheduler,
    shutdown_scheduler,
)
from ops.trades import list_interpreted_trades
from settings import settings


configure_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup")
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        logger.info("Application shutdown")


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class ChannelUpdate(BaseModel):
    enabled: bool


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="ops/home.html",
        context={
            "channel_sync_interval_minutes": settings.CHANNEL_SYNC_INTERVAL_MINUTES,
            "message_sync_interval_minutes": settings.MESSAGE_SYNC_INTERVAL_MINUTES,
            "trade_interpretation_interval_minutes": settings.TRADE_INTERPRETATION_INTERVAL_MINUTES,
            "trade_execution_interval_minutes": settings.TRADE_EXECUTION_INTERVAL_MINUTES,
        },
    )


@app.get("/ops/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    channels = await list_channels()
    return templates.TemplateResponse(
        request=request,
        name="ops/channels.html",
        context={
            "channels": channels,
            "sync_interval_minutes": settings.CHANNEL_SYNC_INTERVAL_MINUTES,
        },
    )


@app.get("/ops/messages-read", response_class=HTMLResponse)
async def messages_read_page(request: Request):
    messages = await list_messages_read()
    return templates.TemplateResponse(
        request=request,
        name="ops/messages_read.html",
        context={
            "messages": messages,
            "message_sync_interval_minutes": settings.MESSAGE_SYNC_INTERVAL_MINUTES,
            "message_sync_lookback_minutes": settings.MESSAGE_SYNC_LOOKBACK_MINUTES,
            "message_sync_limit_per_channel": settings.MESSAGE_SYNC_LIMIT_PER_CHANNEL,
        },
    )


@app.get("/ops/interpreted-trades", response_class=HTMLResponse)
async def interpreted_trades_page(request: Request):
    trades = await list_interpreted_trades()
    return templates.TemplateResponse(
        request=request,
        name="ops/interpreted_trades.html",
        context={
            "trades": trades,
            "trade_interpretation_interval_minutes": settings.TRADE_INTERPRETATION_INTERVAL_MINUTES,
        },
    )


@app.get("/ops/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="ops/jobs.html",
        context={"jobs": list_scheduler_jobs()},
    )


@app.get("/ops/api/channels")
async def channels_api():
    return {"channels": await list_channels()}


@app.patch("/ops/api/channels/{channel_id}")
async def update_channel_api(channel_id: int, payload: ChannelUpdate):
    channel = await set_channel_enabled(channel_id, payload.enabled)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    return {"channel": channel}


@app.post("/ops/api/channels/sync")
async def sync_channels_api():
    try:
        run = await run_scheduler_job(CHANNEL_SYNC_JOB_ID)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Channel sync failed") from exc

    return {"result": run["result"], "job": run["job"], "channels": await list_channels()}


@app.get("/ops/api/messages-read")
async def messages_read_api(limit: int = 200):
    return {"messages": await list_messages_read(limit)}


@app.post("/ops/api/messages-read/sync")
async def sync_messages_read_api():
    try:
        run = await run_scheduler_job(MESSAGE_SYNC_JOB_ID)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Message sync failed") from exc

    return {"result": run["result"], "job": run["job"], "messages": await list_messages_read()}


@app.get("/ops/api/interpreted-trades")
async def interpreted_trades_api(limit: int = 200):
    return {"trades": await list_interpreted_trades(limit)}


@app.get("/ops/api/jobs")
async def jobs_api():
    return {"jobs": list_scheduler_jobs()}


@app.post("/ops/api/jobs/{job_id}/run")
async def run_job_api(job_id: str):
    try:
        run = await run_scheduler_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Scheduled job failed") from exc

    return {"result": run["result"], "job": run["job"], "jobs": list_scheduler_jobs()}


@app.post("/ops/api/trades/interpret")
async def interpret_trades_api():
    try:
        run = await run_scheduler_job(TRADE_INTERPRETATION_JOB_ID)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Trade interpretation failed") from exc

    return {
        "result": run["result"],
        "job": run["job"],
        "messages": await list_messages_read(),
        "trades": await list_interpreted_trades(),
    }
