"""core/logging_config.py
──────────────────────
Centralised logging setup for all Aura modules.

H-12 FIX: RedactionFilter no longer destroys lazy log formatting.
It operates on the final formatted string without clobbering record.args.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# ── Redaction Filter ─────────────────────────────────────────

_REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API tokens / secrets
    (re.compile(r'(sk-[A-Za-z0-9\-_]{20,})', re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-_\.=]{10,}', re.IGNORECASE), r"\1[REDACTED_BEARER]"),
    (re.compile(r'(password["\s:=]+)[^\s"\']+', re.IGNORECASE), r"\1[REDACTED_PASS]"),
    (re.compile(r'(token["\s:=]+)[^\s"\']+', re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Env var values that might slip through
    (re.compile(r'(AURA_API_TOKEN[=:]\s*)\S+'), r"\1[REDACTED]"),
]


class RedactionFilter(logging.Filter):
    """Log filter that scrubs secrets / PII from log records.

    H-12 FIX: Instead of calling getMessage() (which destroys lazy formatting),
    we redact the msg template and individual args separately. This preserves
    the original log record structure for downstream handlers, JSON formatters,
    and log aggregation systems that need to group by message template.
    """

    def __init__(self) -> None:
        super().__init__()
        self._env_token: Optional[str] = None

    def _env_pattern(self) -> Optional[re.Pattern]:
        tok = os.environ.get("AURA_API_TOKEN", "")
        if tok and tok != self._env_token:
            self._env_token = tok
        if self._env_token:
            return re.compile(re.escape(self._env_token))
        return None

    def _redact_string(self, s: str) -> str:
        """Apply all redaction patterns to a string."""
        # Env token redaction
        pat = self._env_pattern()
        if pat:
            s = pat.sub("[REDACTED_ENV_TOKEN]", s)

        # Static pattern redaction
        for pattern, replacement in _REDACT_PATTERNS:
            s = pattern.sub(replacement, s)
        return s

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # Redact the message template (preserves lazy formatting)
        if isinstance(record.msg, str):
            record.msg = self._redact_string(record.msg)

        # Redact individual args if they are strings
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact_string(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact_string(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )

        return True


# ── Formatters ───────────────────────────────────────────────

_CONSOLE_FMT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_CONSOLE_DATE = "%H:%M:%S"

_FILE_FMT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) — %(message)s"
_FILE_DATE = "%Y-%m-%d %H:%M:%S"


class _ColorConsoleFormatter(logging.Formatter):
    """ANSI-coloured formatter for TTY output."""

    COLORS = {
        logging.DEBUG: "\033[2;37m",  # dim white
        logging.INFO: "\033[0;37m",  # white
        logging.WARNING: "\033[0;33m",  # yellow
        logging.ERROR: "\033[0;31m",  # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLORS.get(record.levelno, "")
        reset = self.RESET if colour else ""
        record.levelname = f"{colour}{record.levelname:<8}{reset}"
        return super().format(record)


# ── Main Entry-Point ─────────────────────────────────────────

_initialised: bool = False


def setup_logging(
    name: str = "Aura",
    level: str | int = logging.INFO,
    log_dir: Optional[Path] = None,
    structured: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """Configure root logging and return a named logger.

    Call once at process startup. Subsequent calls return the named logger
    without re-configuring.
    """
    global _initialised

    root = logging.getLogger()

    if not _initialised:
        root.setLevel(level)

        # Redaction filter on root — applies to ALL handlers
        redact = RedactionFilter()
        root.addFilter(redact)

        # ── Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)

        if structured:
            import json as _json

            class _JsonFmt(logging.Formatter):
                def format(self, r: logging.LogRecord) -> str:
                    return _json.dumps(
                        {
                            "ts": self.formatTime(r, datefmt=_FILE_DATE),
                            "level": r.levelname,
                            "name": r.name,
                            "msg": r.getMessage(),
                            "file": f"{r.filename}:{r.lineno}",
                        }
                    )

            ch.setFormatter(_JsonFmt())
        else:
            if sys.stdout.isatty():
                fmt = _ColorConsoleFormatter(_CONSOLE_FMT, datefmt=_CONSOLE_DATE)
            else:
                fmt = logging.Formatter(_CONSOLE_FMT, datefmt=_CONSOLE_DATE)
            ch.setFormatter(fmt)

        root.addHandler(ch)

        # ── File handler (optional)
        if log_dir is not None:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                log_dir / "aura.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_FILE_DATE))
            root.addHandler(fh)

        # Silence noisy third-party loggers
        for noisy in (
            "httpx",
            "httpcore",
            "urllib3",
            "asyncio",
            "uvicorn.access",
        ):
            logging.getLogger(noisy).setLevel(logging.WARNING)

        _initialised = True

    return logging.getLogger(name)


# ── Convenience: get a module logger ─────────────────────────


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)


# ── Reset (for testing) ───────────────────────────────────────


def _reset_for_testing() -> None:
    """Reset initialisation flag and clear all handlers. TEST USE ONLY."""
    global _initialised
    _initialised = False
    root = logging.getLogger()
    root.handlers.clear()
    root.filters.clear()
