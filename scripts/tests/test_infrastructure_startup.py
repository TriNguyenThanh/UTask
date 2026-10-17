"""Exercise startup lifecycle with POSIX fixture children, without Docker writes."""

import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix", "Requires POSIX process signals and shell")
class InfrastructureStartupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def executable(self, name, body):
        path = self.path / name
        path.write_text("#!/bin/sh\nset -eu\n" + body + "\n")
        path.chmod(0o755)
        return str(path)

    def start(self, infrastructure, **overrides):
        child = str(self.path / "child")
        Path(child).write_text(
            "#!/usr/bin/env python3\n"
            "import os, signal, sys, time\n"
            "from pathlib import Path\n"
            "directory = Path(os.environ['FIXTURE_DIR'])\n"
            "def stop(signum, frame):\n"
            "    (directory / 'stopped').write_text('stopped')\n"
            "    sys.exit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "signal.signal(signal.SIGINT, stop)\n"
            "(directory / 'pid').write_text(str(os.getpid()))\n"
            "if os.environ.get('CHILD_EXIT'):\n"
            "    sys.exit(int(os.environ['CHILD_EXIT']))\n"
            "while True:\n"
            "    time.sleep(0.05)\n"
        )
        Path(child).chmod(0o755)
        bootstrap = self.executable(
            "bootstrap",
            'echo bootstrap >> "$FIXTURE_DIR/calls"\n'
            'if [ "${BLOCK_BOOTSTRAP:-0}" = 1 ]; then\n'
            '  echo $$ > "$FIXTURE_DIR/preparation_pid"\n'
            "  exec /bin/sleep 60\nfi\n"
            'exit "${BOOTSTRAP_EXIT:-0}"',
        )
        self.executable("sleep", "exec /bin/sleep 0.02")
        self.executable(
            "pg_isready",
            'test "${NOT_READY:-0}" = 0 && test -f "$FIXTURE_DIR/pid"',
        )
        self.executable("docker-entrypoint.sh", f'exec "{child}" "$@"')
        topics = self.executable(
            "topics",
            'echo "$*" >> "$FIXTURE_DIR/topic_calls"\n'
            'case " $* " in\n'
            '  *" --list "*) test "${NOT_READY:-0}" = 0 && test -f "$FIXTURE_DIR/pid" ;;\n'
            '  *) if [ "${BLOCK_BOOTSTRAP:-0}" = 1 ]; then\n'
            '       echo $$ > "$FIXTURE_DIR/preparation_pid"\n'
            "       exec /bin/sleep 60\n"
            "     fi\n"
            '     exit "${BOOTSTRAP_EXIT:-0}" ;;\nesac',
        )
        marker = self.path / "ready"
        marker.touch()  # A stale marker must never survive a failed restart.
        script = (
            ROOT / f"infra/{infrastructure}/start-{infrastructure}.sh"
        ).read_text()
        script = script.replace(f"/tmp/utask-{infrastructure}-ready", str(marker))
        script = script.replace(
            "/docker-entrypoint-initdb.d/init-databases.sh", bootstrap
        )
        script = script.replace("/etc/kafka/docker/run", child)
        script = script.replace("/opt/kafka/bin/kafka-topics.sh", topics)
        target = self.path / "startup.sh"
        target.write_text(script)
        env = (
            os.environ
            | {
                "PATH": str(self.path) + os.pathsep + os.environ["PATH"],
                "FIXTURE_DIR": str(self.path),
                "POSTGRES_USER": "fixture",
                "POSTGRES_DB": "postgres",
                "POSTGRES_PASSWORD": "fixture",
                "KAFKA_BOOTSTRAP_SERVERS": "configured-broker:19092",
                "WORK_KAFKA_TOPIC": "work.custom",
                "CLASSROOM_KAFKA_TOPIC": "classroom.custom",
                "CLASSROOM_WORK_KAFKA_DLQ_TOPIC": "classroom.dlq",
                "WORK_CLASSROOM_KAFKA_DLQ_TOPIC": "work.dlq",
            }
            | overrides
        )
        process = subprocess.Popen(
            ["/bin/sh", str(target), "postgres"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop, process)
        return process, marker

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)

    def wait_ready(self, process, marker):
        deadline = time.monotonic() + 5
        # Wait for actual bootstrap evidence as well as the readiness marker.
        while time.monotonic() < deadline:
            evidence = any(
                (self.path / name).exists() for name in ("topic_calls", "calls")
            )
            if marker.exists() and evidence:
                return
            if process.poll() is not None:
                self.fail(process.communicate()[1])
            time.sleep(0.01)
        self.fail("Startup did not become ready")

    def assert_child_stopped(self):
        pid = int((self.path / "pid").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_success_creates_marker_and_term_stops_child_for_both_services(self):
        for infrastructure in ("postgres", "kafka"):
            with self.subTest(infrastructure=infrastructure):
                process, marker = self.start(infrastructure)
                self.wait_ready(process, marker)
                process.send_signal(signal.SIGTERM)
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 143, stderr)
                self.assertFalse(marker.exists())
                self.assert_child_stopped()
                self.assertTrue((self.path / "stopped").exists())
                for name in ("pid", "calls", "topic_calls", "stopped"):
                    (self.path / name).unlink(missing_ok=True)

    def test_bootstrap_failure_removes_marker_and_stops_child(self):
        for infrastructure in ("postgres", "kafka"):
            with self.subTest(infrastructure=infrastructure):
                process, marker = self.start(infrastructure, BOOTSTRAP_EXIT="7")
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 7, stderr)
                self.assertFalse(marker.exists())
                self.assert_child_stopped()
                (self.path / "pid").unlink()

    def test_not_ready_has_bounded_failure_and_stops_child(self):
        for infrastructure in ("postgres", "kafka"):
            with self.subTest(infrastructure=infrastructure):
                process, marker = self.start(infrastructure, NOT_READY="1")
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 1, stderr)
                self.assertIn("did not become ready", stderr)
                self.assertFalse(marker.exists())
                self.assert_child_stopped()
                (self.path / "pid").unlink()

    def test_child_early_exit_propagates_status_without_waiting_forever(self):
        for infrastructure in ("postgres", "kafka"):
            with self.subTest(infrastructure=infrastructure):
                process, marker = self.start(
                    infrastructure, CHILD_EXIT="9", NOT_READY="1"
                )
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 9, stderr)
                self.assertFalse(marker.exists())
                self.assert_child_stopped()
                (self.path / "pid").unlink()

    def test_term_during_readiness_stops_child_without_publishing_ready(self):
        for infrastructure in ("postgres", "kafka"):
            with self.subTest(infrastructure=infrastructure):
                process, marker = self.start(infrastructure, NOT_READY="1")
                deadline = time.monotonic() + 3
                while not (self.path / "pid").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((self.path / "pid").exists())
                process.terminate()
                _, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 143, stderr)
                self.assertFalse(marker.exists())
                self.assert_child_stopped()
                (self.path / "pid").unlink()

    def test_term_during_preparation_stops_preparation_and_server_promptly(self):
        for infrastructure in ("postgres", "kafka"):
            with self.subTest(infrastructure=infrastructure):
                process, marker = self.start(infrastructure, BLOCK_BOOTSTRAP="1")
                preparation = self.path / "preparation_pid"
                deadline = time.monotonic() + 3
                while not preparation.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(preparation.exists())
                preparation_pid = int(preparation.read_text())
                process.terminate()
                _, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 143, stderr)
                self.assertFalse(marker.exists())
                self.assert_child_stopped()
                with self.assertRaises(ProcessLookupError):
                    os.kill(preparation_pid, 0)
                for name in (
                    "pid",
                    "preparation_pid",
                    "calls",
                    "topic_calls",
                    "stopped",
                ):
                    (self.path / name).unlink(missing_ok=True)

    def test_kafka_creates_four_topics_on_configured_broker_after_local_readiness(self):
        process, marker = self.start("kafka")
        self.wait_ready(process, marker)
        calls = (self.path / "topic_calls").read_text().splitlines()
        self.assertIn("--bootstrap-server localhost:9092 --list", calls[0])
        creates = [call for call in calls if "--create" in call]
        self.assertEqual(len(creates), 4)
        for call, topic in zip(
            creates,
            ("work.custom", "classroom.custom", "classroom.dlq", "work.dlq"),
            strict=True,
        ):
            self.assertIn("--bootstrap-server configured-broker:19092", call)
            self.assertIn("--if-not-exists", call)
            self.assertTrue(call.endswith(f"--topic {topic}"))
