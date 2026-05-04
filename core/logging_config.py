import logging
import logging.config
import traceback
from pathlib import Path


LOG_FORMAT = (
    "%(asctime)s %(levelname)s [%(name)s] "
    "%(filename)s:%(lineno)d %(funcName)s() - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SourceFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        exc = _exception_from_record(record)
        if exc is None:
            return message

        return f"{message}\nException source: {format_exception_source(exc)}"


def configure_logging(level: str) -> None:
    normalized_level = _normalize_level(level)
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "source": {
                    "()": SourceFormatter,
                    "format": LOG_FORMAT,
                    "datefmt": DATE_FORMAT,
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "source",
                    "stream": "ext://sys.stderr",
                }
            },
            "root": {
                "level": normalized_level,
                "handlers": ["console"],
            },
            "loggers": {
                "apscheduler": {
                    "level": normalized_level,
                    "handlers": ["console"],
                    "propagate": False,
                },
                "engineio": {
                    "level": "WARNING",
                    "handlers": ["console"],
                    "propagate": False,
                },
                "socketio": {
                    "level": "WARNING",
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn": {
                    "level": normalized_level,
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": normalized_level,
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": normalized_level,
                    "handlers": ["console"],
                    "propagate": False,
                },
            },
        }
    )


def format_exception_source(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "origin=unknown parent=unknown"

    origin = frames[-1]
    parent = frames[-2] if len(frames) > 1 else None
    parent_text = _format_frame(parent) if parent is not None else "unknown"
    return f"origin={_format_frame(origin)} parent={parent_text}"


def _format_frame(frame: traceback.FrameSummary) -> str:
    return f"{Path(frame.filename).name}:{frame.lineno} {frame.name}()"


def _exception_from_record(record: logging.LogRecord) -> BaseException | None:
    if not record.exc_info:
        return None

    if isinstance(record.exc_info, tuple) and len(record.exc_info) >= 2:
        exc = record.exc_info[1]
        return exc if isinstance(exc, BaseException) else None

    return record.exc_info if isinstance(record.exc_info, BaseException) else None


def _normalize_level(level: str) -> str:
    normalized = level.upper()
    known_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
    return normalized if normalized in known_levels else "INFO"
