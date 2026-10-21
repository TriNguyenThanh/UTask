"""Run Work's existing consumers together without sharing offsets or retry state."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run Identity, Classroom and enabled Integration consumers in one container."

    def handle(self, *args, **options):
        commands = ["consume_classroom"]
        if settings.IDENTITY_KAFKA_TOPIC:
            commands.append("consume_identity")
        if settings.INTEGRATION_ADAPTER != "infrastructure.integration.UnavailableIntegration":
            commands.append("consume_integration")

        stopped = Event()
        previous = {}
        children = []

        def stop(signum, frame):
            stopped.set()

        try:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.signal(signum, stop)
            for command in commands:
                if stopped.is_set():
                    break
                process = subprocess.Popen(
                    [sys.executable, "manage.py", command],
                    cwd=Path(__file__).resolve().parents[4],
                    stdin=subprocess.DEVNULL,
                )
                children.append((command, process))
            while not stopped.wait(0.5):
                for command, process in children:
                    if process.poll() is not None:
                        raise CommandError(f"Work consumer stopped: {command}")
        finally:
            # SIGINT lets each command finish its current handler and close Kafka.
            for _, process in children:
                if process.poll() is None:
                    try:
                        if os.name == "nt":
                            process.terminate()
                        else:
                            process.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        pass
            deadline = time.monotonic() + 10
            try:
                for _, process in children:
                    try:
                        process.wait(timeout=max(0, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
