"""Queue-backed JSON operational logs and readable terminal trade output."""

import json
import logging
import logging.handlers
import queue
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Emit one structured JSON object per operational event."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class StreamFilter(logging.Filter):
    def __init__(self, trades: bool) -> None:
        super().__init__()
        self.trades = trades

    def filter(self, record: logging.LogRecord) -> bool:
        return (record.name == "marketpulse.trades") == self.trades


def configure_logging(level: str) -> logging.handlers.QueueListener:
    """Offload terminal output to a listener thread; caller must stop the listener."""
    messages: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    handler = logging.handlers.QueueHandler(messages)
    logger = logging.getLogger("marketpulse")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    trades = logging.getLogger("marketpulse.trades")
    trades.setLevel(logging.INFO)
    operational = logging.StreamHandler(sys.stderr)
    operational.setFormatter(JsonFormatter())
    operational.addFilter(StreamFilter(False))
    terminal = logging.StreamHandler(sys.stdout)
    terminal.setFormatter(logging.Formatter("%(message)s"))
    terminal.addFilter(StreamFilter(True))
    listener = logging.handlers.QueueListener(messages, operational, terminal)
    listener.start()
    return listener
