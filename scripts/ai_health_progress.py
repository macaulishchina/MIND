"""Helpers for streaming pytest progress in the AI health check."""

from __future__ import annotations

import math
import re
import selectors
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PYTEST_PROGRESS_REFRESH_SECONDS = 1.0

_XDIST_RESULT_RE = re.compile(
    r"\[(gw\d+)\]\s+\[\s*\d+%\]\s+(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\s+(.*)",
)
_SERIAL_RESULT_RE = re.compile(
    r"(\S+::\S+)\s+(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\s+\[\s*\d+%\]",
)
_PYTEST_START_RE = re.compile(r"^(\S+::\S+)\s*$")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class WorkerState:
    """Per-worker progress state."""

    done: int
    fail: int
    first_seen: float
    last_update: float
    current_test: str = ""


class PytestProgressBar:
    """Multi-line terminal progress bar for streaming pytest runs."""

    _WORKER_BAR_WIDTH = 24
    _RUNNING_IDLE_THRESHOLD_SECONDS = 1.5

    def __init__(self, total: int, worker_count: int) -> None:
        self.total = max(total, 1)
        self.worker_count = worker_count
        self.completed = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.errors = 0
        self.workers: dict[str, WorkerState] = {}
        self.start = time.monotonic()
        self._prev_visual_rows = 0
        self.finalizing = False
        self.started_tests: dict[str, float] = {}
        self.longest_observed_test: tuple[str, float] | None = None

    def update(self, worker_id: str, outcome: str) -> None:
        """Record a test completion and re-render."""
        now = time.monotonic()
        self.completed += 1
        up = outcome.upper()
        if up in ("PASSED", "XPASS"):
            self.passed += 1
        elif up == "FAILED":
            self.failed += 1
        elif up in ("SKIPPED", "XFAIL"):
            self.skipped += 1
        elif up == "ERROR":
            self.errors += 1

        worker = self._get_or_create_worker(worker_id, now=now)
        worker.done += 1
        worker.last_update = now
        if up in ("FAILED", "ERROR"):
            worker.fail += 1
        worker.current_test = ""
        self.render()

    def note_test_start(self, nodeid: str, worker_id: str | None = None) -> None:
        """Record that a test has started running."""
        nodeid = self._normalize_nodeid(nodeid)
        self.started_tests[nodeid] = time.monotonic()
        if worker_id is None:
            self.render()
            return
        worker = self._get_or_create_worker(worker_id)
        worker.current_test = nodeid
        self.render()

    def render(self) -> None:
        """Redraw the entire progress display in place."""
        lines = self._build_lines()
        visual_rows = sum(self._visual_rows(line) for line in lines)
        if self._prev_visual_rows > 0:
            sys.stdout.write(f"\x1b[{self._prev_visual_rows}F")
            sys.stdout.write("\x1b[J")
        for line in lines:
            sys.stdout.write(f"\x1b[2K{line}\n")
        sys.stdout.flush()
        self._prev_visual_rows = visual_rows

    def finish(self) -> None:
        """Collapse the multi-line display into a single summary line."""
        elapsed = time.monotonic() - self.start
        if self._prev_visual_rows > 0:
            sys.stdout.write(f"\x1b[{self._prev_visual_rows}F")
            sys.stdout.write("\x1b[J")
        summary = (
            f"  ⏳ {self.completed}/{self.total} tests"
            f" ({self.worker_count}w, {elapsed:.1f}s)"
            f"  ✅{self.passed} ❌{self.failed} ⏭{self.skipped}"
        )
        sys.stdout.write(f"\x1b[2K{summary}\n")
        sys.stdout.flush()
        self._prev_visual_rows = 0

    def set_finalizing(self, finalizing: bool) -> None:
        """Mark whether pytest is finalizing after all test results arrived."""
        self.finalizing = finalizing
        self.render()

    def bind_completed_test(self, worker_id: str, nodeid: str) -> None:
        """Clear a completed nodeid from worker state when applicable."""
        nodeid = self._normalize_nodeid(nodeid)
        now = time.monotonic()
        worker = self._get_or_create_worker(worker_id, now=now)
        started_at = self.started_tests.get(nodeid)
        if started_at is not None:
            duration = max(now - started_at, 0.0)
            if self.longest_observed_test is None or duration >= self.longest_observed_test[1]:
                self.longest_observed_test = (nodeid, duration)
        self.started_tests.pop(nodeid, None)
        if worker.current_test == nodeid:
            worker.current_test = ""

    def _build_lines(self) -> list[str]:
        lines: list[str] = []
        pct = self.completed / self.total
        elapsed = time.monotonic() - self.start
        bar_w = 30
        filled = int(bar_w * pct)
        bar = "█" * filled + "░" * (bar_w - filled)
        pct_label = self._format_progress_percent(pct)

        lines.append(self._build_worker_summary_line())
        lines.append(
            f"  ⏳ [{bar}] {pct_label:>5}  "
            f"{self.completed}/{self.total}  "
            f"✅{self.passed} ❌{self.failed} ⏭{self.skipped}  "
            f"⏱ total {elapsed:.0f}s"
        )
        longest_observed = self._longest_observed_test()
        if self.worker_count > 1 and longest_observed is not None:
            nodeid, duration = longest_observed
            lines.append(
                "  📝 longest observed │ "
                f"{self._short_nodeid(nodeid)}  {duration:.0f}s"
            )
        if self.worker_count > 1:
            lines.append("  📦 workers │")
            for worker_id in sorted(self._all_worker_ids(), key=self._worker_sort_key):
                lines.append(f"          │ {self._format_worker_cell(worker_id)}")
        else:
            lines.append("  📦 workers │")
            lines.append(f"          │ {self._format_worker_cell('main')}")
        return lines

    def _build_worker_summary_line(self) -> str:
        active_workers = sum(1 for wid in self._all_worker_ids() if self._worker_is_active(wid))
        idle_workers = max(self.worker_count - active_workers, 0)
        average = self.completed / self.worker_count if self.worker_count else 0.0
        worker_ids = self._all_worker_ids()
        if active_workers == 0:
            return (
                f"  🧵 workers │ total {self.worker_count}  active 0  "
                f"idle {idle_workers}  avg {average:.1f}/w  collecting..."
            )
        busiest = max(
            worker_ids,
            key=lambda wid: (self._worker_done(wid), self._worker_sort_key(wid)),
        )
        quietest = min(
            worker_ids,
            key=lambda wid: (self._worker_done(wid), self._worker_sort_key(wid)),
        )
        imbalance = self._worker_done(busiest) / average if average else 0.0
        return (
            f"  🧵 workers │ total {self.worker_count}  active {active_workers}  "
            f"idle {idle_workers}  avg {average:.1f}/w  "
            f"max {busiest}:{self._worker_done(busiest)}  "
            f"min {quietest}:{self._worker_done(quietest)}  "
            f"imbalance {imbalance:.2f}x"
        )

    def _format_worker_cell(self, worker_id: str) -> str:
        done = self._worker_done(worker_id)
        share = done / self.completed if self.completed else 0.0
        bar = self._worker_bar(done)
        status = self._worker_status(worker_id)
        duration = self._worker_elapsed(worker_id)
        label = f"{worker_id}:{done:>3}".ljust(self._worker_label_width())
        cell = f"{label} [{bar}] {share:>4.0%}  {status:<8} {duration:>4.0f}s"
        current_test = self._worker_current_test(worker_id)
        if status == "running" and current_test:
            cell += f"  {self._short_nodeid(current_test)}"
        if self._worker_failures(worker_id):
            return f"\x1b[31m{cell}\x1b[0m"
        return cell

    def _worker_status(self, worker_id: str) -> str:
        worker = self._worker_state(worker_id)
        if self.finalizing:
            return "teardown"
        if self._worker_current_test(worker_id):
            return "running"
        if worker is None or worker.done == 0:
            return "waiting"
        if time.monotonic() - worker.last_update <= self._RUNNING_IDLE_THRESHOLD_SECONDS:
            return "running"
        return "idle"

    def _worker_elapsed(self, worker_id: str) -> float:
        worker = self._worker_state(worker_id)
        if worker is None:
            return 0.0
        if self._worker_status(worker_id) == "running":
            return max(time.monotonic() - worker.first_seen, 0.0)
        return max(worker.last_update - worker.first_seen, 0.0)

    def _worker_bar(self, done: int) -> str:
        max_done = max((self._worker_done(wid) for wid in self._all_worker_ids()), default=0)
        if max_done <= 0 or done <= 0:
            return "░" * self._WORKER_BAR_WIDTH
        filled = round((done / max_done) * self._WORKER_BAR_WIDTH)
        filled = min(max(filled, 1), self._WORKER_BAR_WIDTH)
        return "█" * filled + "░" * (self._WORKER_BAR_WIDTH - filled)

    def _worker_label_width(self) -> int:
        return max(len(f"{wid}:{self._worker_done(wid):>3}") for wid in self._all_worker_ids())

    def _worker_done(self, worker_id: str) -> int:
        worker = self._worker_state(worker_id)
        return worker.done if worker is not None else 0

    def _worker_failures(self, worker_id: str) -> int:
        worker = self._worker_state(worker_id)
        return worker.fail if worker is not None else 0

    def _worker_current_test(self, worker_id: str) -> str:
        worker = self._worker_state(worker_id)
        return worker.current_test if worker is not None else ""

    def _worker_is_active(self, worker_id: str) -> bool:
        return self._worker_done(worker_id) > 0 or bool(self._worker_current_test(worker_id))

    def _all_worker_ids(self) -> list[str]:
        if self.worker_count <= 1:
            return ["main"]
        return [f"gw{index}" for index in range(self.worker_count)]

    def _get_or_create_worker(self, worker_id: str, *, now: float | None = None) -> WorkerState:
        stamp = time.monotonic() if now is None else now
        worker = self._worker_state(worker_id)
        if worker is not None:
            self.workers[worker_id] = worker
            return worker
        created = WorkerState(done=0, fail=0, first_seen=stamp, last_update=stamp)
        self.workers[worker_id] = created
        return created

    def _worker_state(self, worker_id: str) -> WorkerState | None:
        """Return normalized worker state, accepting legacy dict fixtures."""
        worker = self.workers.get(worker_id)
        if worker is None:
            return None
        if isinstance(worker, WorkerState):
            return worker
        if isinstance(worker, dict):
            normalized = WorkerState(
                done=int(worker.get("done", 0)),
                fail=int(worker.get("fail", 0)),
                first_seen=float(worker.get("first_seen", 0.0)),
                last_update=float(worker.get("last_update", 0.0)),
                current_test=str(worker.get("current_test", "")),
            )
            self.workers[worker_id] = normalized
            return normalized
        return None

    def _worker_sort_key(self, worker_id: str) -> int:
        if worker_id.startswith("gw"):
            return int(worker_id.removeprefix("gw"))
        return -1

    def _short_nodeid(self, nodeid: str) -> str:
        nodeid = self._normalize_nodeid(nodeid)
        parts = nodeid.split("::")
        if len(parts) >= 2:
            return f"{parts[-2].split('/')[-1]}::{parts[-1]}"
        return nodeid.split("/")[-1]

    def _normalize_nodeid(self, nodeid: str) -> str:
        return nodeid.strip()

    def _format_progress_percent(self, pct: float) -> str:
        if pct >= 1.0:
            return "100%"
        return f"{math.floor(pct * 100):>2d}%"

    def _visual_rows(self, line: str) -> int:
        width = self._terminal_columns()
        visible = _ANSI_ESCAPE_RE.sub("", line)
        return max(1, math.ceil(max(len(visible), 1) / width))

    def _terminal_columns(self) -> int:
        return max(shutil.get_terminal_size(fallback=(120, 24)).columns, 20)

    def _longest_observed_test(self) -> tuple[str, float] | None:
        active_longest: tuple[str, float] | None = None
        if self.started_tests:
            now = time.monotonic()
            nodeid, started_at = min(self.started_tests.items(), key=lambda item: item[1])
            active_longest = (nodeid, max(now - started_at, 0.0))
        if self.longest_observed_test is None:
            return active_longest
        if active_longest is None:
            return self.longest_observed_test
        if active_longest[1] >= self.longest_observed_test[1]:
            return active_longest
        return self.longest_observed_test


def collect_test_count(
    base_cmd: list[str],
    env: dict[str, str],
    run_command: Callable[..., tuple[int, str, str]],
) -> int:
    """Run pytest --collect-only to determine total test count."""
    filtered: list[str] = []
    skip_next = False
    for tok in base_cmd:
        if skip_next:
            skip_next = False
            continue
        if tok in ("-n", "--dist"):
            skip_next = True
            continue
        if tok in ("-x", "-q", "--no-header", "--tb=short"):
            continue
        if tok.startswith("--timeout"):
            continue
        filtered.append(tok)
    filtered.extend(["--collect-only", "-q"])
    code, stdout, stderr = run_command(filtered, timeout=60, env=env)
    del code
    for line in reversed((stdout + stderr).splitlines()):
        match = re.search(r"(\d+)\s+test", line)
        if match:
            return int(match.group(1))
    return 0


def build_verbose_command(base_cmd: list[str]) -> list[str]:
    """Convert a -q/--no-header pytest command to -v for progress tracking."""
    out: list[str] = []
    for tok in base_cmd:
        if tok in ("-q", "--no-header"):
            continue
        out.append(tok)
    out.append("-v")
    return out


def detect_worker_count(cmd: list[str]) -> int:
    """Extract the -n worker count from a pytest command, default 1."""
    for i, tok in enumerate(cmd):
        if tok == "-n" and i + 1 < len(cmd):
            try:
                return int(cmd[i + 1])
            except ValueError:
                return 1
    return 1


def run_with_progress(
    cmd: list[str],
    total: int,
    worker_count: int,
    *,
    env: dict[str, str],
    timeout: int,
) -> tuple[int, str]:
    """Stream pytest output with a live progress bar, return (code, output)."""
    bar = PytestProgressBar(total, worker_count)
    bar.render()
    collected: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
    except FileNotFoundError:
        bar.finish()
        return -2, f"Command not found: {cmd[0]}"

    deadline = time.monotonic() + timeout
    next_refresh = time.monotonic() + PYTEST_PROGRESS_REFRESH_SECONDS
    selector = selectors.DefaultSelector()
    try:
        assert proc.stdout is not None
        selector.register(proc.stdout, selectors.EVENT_READ)
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                bar.finish()
                collected.append(f"\nTimed out after {timeout}s")
                return -1, "\n".join(collected)

            now = time.monotonic()
            timeout_left = max(0.0, min(next_refresh - now, deadline - now))
            events = selector.select(timeout=timeout_left)

            if not events:
                if proc.poll() is not None:
                    break
                if time.monotonic() >= next_refresh:
                    bar.render()
                    next_refresh = time.monotonic() + PYTEST_PROGRESS_REFRESH_SECONDS
                continue

            for key, _mask in events:
                fileobj: Any = key.fileobj
                if not hasattr(fileobj, "readline"):
                    continue
                raw_line = fileobj.readline()
                if raw_line == "":
                    selector.unregister(fileobj)
                    if bar.completed >= total and proc.poll() is None:
                        bar.set_finalizing(True)
                    continue
                line = raw_line.rstrip("\n")
                collected.append(line)

                match = _XDIST_RESULT_RE.match(line)
                if match:
                    bar.bind_completed_test(match.group(1), match.group(3))
                    bar.update(match.group(1), match.group(2))
                    next_refresh = time.monotonic() + PYTEST_PROGRESS_REFRESH_SECONDS
                    continue

                match = _SERIAL_RESULT_RE.search(line)
                if match:
                    bar.bind_completed_test("main", match.group(1))
                    bar.update("main", match.group(2))
                    next_refresh = time.monotonic() + PYTEST_PROGRESS_REFRESH_SECONDS
                    continue

                match = _PYTEST_START_RE.match(line.strip())
                if match:
                    bar.set_finalizing(False)
                    worker_id = "main" if worker_count <= 1 else None
                    bar.note_test_start(match.group(1), worker_id=worker_id)
                    next_refresh = time.monotonic() + PYTEST_PROGRESS_REFRESH_SECONDS
                    continue

                if bar.completed >= total and proc.poll() is None:
                    bar.set_finalizing(True)

        remaining = max(1, int(deadline - time.monotonic()))
        proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        proc.kill()
        bar.finish()
        collected.append(f"\nTimed out after {timeout}s")
        return -1, "\n".join(collected)
    finally:
        selector.close()
        bar.finish()

    return proc.returncode or 0, "\n".join(collected)
