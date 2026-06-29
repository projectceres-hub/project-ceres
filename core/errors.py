"""
core/errors.py — Project Ceres
================================
Global error handling and crash diagnostics for the GM Assistant.

Captures unhandled exceptions (including those thrown in background scheduler
threads), logs full tracebacks to logs/errors.log, and wraps the main entry
point so crashes-on-close are recorded rather than swallowed silently.

Usage (in assistant.py):
    from core.errors import install_error_handler, guarded_main

    install_error_handler()   # call before anything else in main()
    guarded_main(main)        # replaces the bare main() call at the bottom
"""

import sys
import os
import traceback
import logging
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Log file setup
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = _PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "errors.log"


def _setup_logger() -> logging.Logger:
    """Create a rotating file logger for crash/error events."""
    logger = logging.getLogger("project_ceres.errors")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger  # Already configured — avoid duplicate handlers on reload

    # Rotating: 5 MB per file, keep 3 backups → ~15 MB max
    file_formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s\n%(message)s\n" + "-" * 60,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_log_error = None
    try:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        file_log_error = exc

    # Echo WARNING and above to stderr so they also appear in the terminal
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console_handler)

    if file_log_error is not None:
        logger.warning(
            "Could not open crash log file %s: %s",
            LOG_FILE,
            file_log_error,
        )

    return logger


_logger = _setup_logger()


# ---------------------------------------------------------------------------
# Exception hooks
# ---------------------------------------------------------------------------

def _handle_exception(exc_type, exc_value, exc_tb) -> None:
    """
    Replacement for sys.excepthook.
    Logs the full traceback to errors.log before the process exits.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        # Let Ctrl-C exit cleanly — don't log these as crashes
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    _logger.critical(
        "UNHANDLED EXCEPTION (main thread)\n"
        f"Type:    {exc_type.__name__}\n"
        f"Message: {exc_value}\n\n"
        f"{tb_str}"
    )
    print(
        f"\n[ERROR] An unexpected error occurred: {exc_type.__name__}: {exc_value}"
        f"\nFull traceback saved to: {LOG_FILE}\n",
        file=sys.stderr
    )

    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _handle_thread_exception(args: threading.ExceptHookArgs) -> None:
    """
    Catches unhandled exceptions in background threads (scheduler, etc.).
    Without this, thread crashes are completely silent.
    """
    if args.exc_type is None or issubclass(args.exc_type, SystemExit):
        return

    tb_str = "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    thread_name = getattr(args.thread, "name", str(args.thread))

    _logger.error(
        f"UNHANDLED EXCEPTION IN THREAD: {thread_name}\n"
        f"Type:    {args.exc_type.__name__}\n"
        f"Message: {args.exc_value}\n\n"
        f"{tb_str}"
    )
    print(
        f"\n[ERROR] Background thread '{thread_name}' crashed: "
        f"{args.exc_type.__name__}: {args.exc_value}"
        f"\nFull traceback saved to: {LOG_FILE}\n",
        file=sys.stderr
    )


def _handle_unraisable(unraisable) -> None:
    """
    Catches exceptions in __del__ and other contexts where they can't be
    raised normally (e.g. during garbage collection on shutdown).
    This is the most likely source of a silent crash-on-close.
    """
    if unraisable.exc_value is None:
        return

    tb_str = traceback.format_exception(
        type(unraisable.exc_value),
        unraisable.exc_value,
        unraisable.exc_value.__traceback__,
    )
    _logger.error(
        f"UNRAISABLE EXCEPTION (likely during shutdown/GC)\n"
        f"Object:  {unraisable.object!r}\n"
        f"Message: {unraisable.exc_value}\n\n"
        f"{''.join(tb_str)}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_error_handler() -> None:
    """
    Install all global exception hooks.

    Call this at the very top of main(), before any other setup, so that
    errors during initialization are also captured.
    """
    sys.excepthook = _handle_exception
    threading.excepthook = _handle_thread_exception

    if hasattr(sys, "unraisablehook"):
        sys.unraisablehook = _handle_unraisable

    _logger.info(
        f"GM Assistant starting — error handler active "
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n"
        f"Log file: {LOG_FILE}"
    )


def guarded_main(main_func: Callable[[], None]) -> None:
    """
    Run main_func inside a try/except so that any exception thrown during
    startup, the command loop, or shutdown teardown is captured before exit.

    Args:
        main_func: The main() function to wrap.

    Usage:
        if __name__ == "__main__":
            guarded_main(main)
    """
    try:
        main_func()
    except KeyboardInterrupt:
        print("\nExiting GM Assistant. Goodbye!")
    except SystemExit:
        raise  # Let sys.exit() propagate normally
    except Exception:
        tb_str = traceback.format_exc()
        _logger.critical(
            "CRASH IN MAIN\n"
            f"{tb_str}"
        )
        print(
            f"\n[CRASH] GM Assistant crashed during shutdown or startup."
            f"\nFull traceback saved to: {LOG_FILE}\n",
            file=sys.stderr
        )
        sys.exit(1)


def log_warning(message: str, context: str = "") -> None:
    """
    Log a non-fatal warning from anywhere in the app.

    Args:
        message: Description of the warning.
        context: Optional module/function name for context.

    Usage:
        from core.errors import log_warning
        log_warning("SRD index is empty — run 'srd-index' to rebuild", context="occator")
    """
    _logger.warning(f"[{context}] {message}" if context else message)


def log_error(message: str, exc: Exception = None, context: str = "") -> None:
    """
    Log a handled (non-fatal) error from anywhere in the app.

    Args:
        message: Description of the error.
        exc: Optional exception instance for traceback capture.
        context: Optional module/function name for context.

    Usage:
        from core.errors import log_error
        try:
            schedule_session()
        except Exception as e:
            log_error("Failed to write .ics file", exc=e, context="promitor")
    """
    prefix = f"[{context}] " if context else ""
    if exc:
        tb_str = traceback.format_exc()
        _logger.error(
            f"{prefix}{message}\n"
            f"Exception: {type(exc).__name__}: {exc}\n"
            f"{tb_str}"
        )
    else:
        _logger.error(f"{prefix}{message}")
