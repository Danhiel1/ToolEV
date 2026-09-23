#!/usr/bin/env python3
"""
ToolEV Centralized Logging & Error Diagnostics Module.
Configures rotating file logging to toolev.log and stream logging.
Installs uncaught exception handlers for main and background threads.
"""
import os
import sys
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "toolev.log"

_INITIALIZED = False
_INIT_LOCK = threading.Lock()


def setup_logging(log_file: Path = None, level=logging.INFO, max_bytes=5 * 1024 * 1024, backup_count=3):
    global _INITIALIZED
    with _INIT_LOCK:
        if _INITIALIZED:
            return

        target_log = Path(log_file) if log_file else LOG_FILE
        target_log.parent.mkdir(parents=True, exist_ok=True)

        root_logger = logging.getLogger("toolev")
        root_logger.setLevel(level)

        # Tránh thêm lặp handlers
        if root_logger.handlers:
            root_logger.handlers.clear()

        # Formatter chuẩn
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 1. Rotating File Handler (UTF-8, an toàn khi chạy windowless/pythonw)
        try:
            file_handler = RotatingFileHandler(
                str(target_log),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            try:
                sys.stderr.write(f"Failed to setup file handler for logging: {e}\n")
            except Exception:
                pass

        # 2. Stream Handler (nếu stderr/stdout khả dụng)
        try:
            if sys.stderr is not None:
                stream_handler = logging.StreamHandler(sys.stderr)
                stream_handler.setLevel(level)
                stream_handler.setFormatter(formatter)
                root_logger.addHandler(stream_handler)
        except Exception:
            pass

        # 3. Cài đặt hook bắt lỗi toàn diện cho uncaught exceptions
        _install_exception_hooks(root_logger)

        _INITIALIZED = True
        root_logger.info("=== ToolEV Logging Initialized (PID: %s, Log: %s) ===", os.getpid(), target_log)


def _install_exception_hooks(logger):
    """Bắt toàn bộ exception chưa xử lý ở main thread và background threads"""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("❌ Uncaught exception in main process:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        def handle_thread_exception(args):
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            logger.critical(
                f"❌ Uncaught exception in thread '{args.thread.name}':",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
            )
        threading.excepthook = handle_thread_exception


def get_logger(name: str = "") -> logging.Logger:
    """Lấy logger con hoặc logger chính của ToolEV"""
    if not _INITIALIZED:
        setup_logging()
    if name:
        return logging.getLogger(f"toolev.{name}")
    return logging.getLogger("toolev")


def get_log_file_path() -> Path:
    return LOG_FILE


def get_recent_logs(max_lines: int = 200) -> list:
    """Đọc an toàn max_lines dòng log gần nhất từ toolev.log"""
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip("\r\n") for line in lines[-max_lines:]]
    except Exception as e:
        return [f"[Error reading log file: {e}]"]


def get_raw_logs() -> str:
    """Trả về toàn bộ nội dung text của file log"""
    if not LOG_FILE.exists():
        return f"No log file found at {LOG_FILE}"
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading log file: {e}"


def clear_logs() -> bool:
    """Xóa sạch nội dung file log"""
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"=== ToolEV Log Cleared (PID: {os.getpid()}) ===\n")
        return True
    except Exception as e:
        get_logger().error(f"Failed to clear log file: {e}")
        return False
