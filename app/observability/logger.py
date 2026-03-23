"""
Structured JSON logging via structlog.
All logs include: timestamp, level, trace_id, context.
Writes to /data/logs/ and stdout.
Override log dir via HA_LOGS_DIR env var.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog

LOGS_DIR = Path(os.environ.get("HA_LOGS_DIR", "/data/logs"))


def setup_logging(log_level: str = "info") -> None:
    """Initialize structlog with JSON output to file and stdout."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    log_file = LOGS_DIR / "ha_copilot.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    for handler in [file_handler, stdout_handler]:
        handler.setFormatter(formatter)

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=[file_handler, stdout_handler],
        force=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog bound logger."""
    return structlog.get_logger(name)
