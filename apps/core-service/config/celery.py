import os
import threading
import time
from pathlib import Path

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

HEARTBEAT_FILE = Path(os.environ.get("CORE_WORKER_HEARTBEAT_FILE", "/tmp/core-worker.heartbeat"))
HEARTBEAT_INTERVAL_SECONDS = float(os.environ.get("CORE_WORKER_HEARTBEAT_INTERVAL_SECONDS", "5"))

_heartbeat_stop = threading.Event()
_heartbeat_thread: threading.Thread | None = None


def write_heartbeat(path: Path = HEARTBEAT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{time.time():.6f}\n", encoding="utf-8")


def is_heartbeat_fresh(path: Path = HEARTBEAT_FILE, max_age_seconds: float = 30.0) -> bool:
    if not path.is_file():
        return False
    try:
        recorded = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return (time.time() - recorded) < max_age_seconds


def _heartbeat_loop(path: Path, interval: float, stop_event: threading.Event) -> None:
    while not stop_event.wait(interval):
        try:
            write_heartbeat(path)
        except OSError:
            continue


@worker_ready.connect
def start_heartbeat(
    path: Path | None = None, interval: float | None = None, **_kwargs
) -> threading.Thread:
    global _heartbeat_thread
    target_path = path or HEARTBEAT_FILE
    target_interval = HEARTBEAT_INTERVAL_SECONDS if interval is None else interval
    _heartbeat_stop.clear()
    write_heartbeat(target_path)
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(target_path, target_interval, _heartbeat_stop),
        name="core-worker-heartbeat",
        daemon=True,
    )
    _heartbeat_thread.start()
    return _heartbeat_thread


@worker_shutdown.connect
def stop_heartbeat(path: Path | None = None, **_kwargs) -> None:
    global _heartbeat_thread
    target_path = path or HEARTBEAT_FILE
    _heartbeat_stop.set()
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        _heartbeat_thread.join(timeout=2.0)
    _heartbeat_thread = None
    target_path.unlink(missing_ok=True)
