# Ответственные участники: Осмонов Медер (А), Адылов Арсен (Б), Кашымбеков Актан (В)
"""Discrete single-CPU scheduling, integer time, Python 3.11+, no dependencies."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    pid: str | None


@dataclass(frozen=True)
class Metrics:
    pid: str
    arrival: int
    burst: int
    priority: int
    start: int
    completion: int
    waiting: int
    turnaround: int
    response: int


@dataclass
class Result:
    algorithm: str
    processes: list[Process]
    timeline: list[Segment]
    metrics: list[Metrics]
    dispatches: int

    def average(self, field: str) -> float:
        return sum(getattr(m, field) for m in self.metrics) / len(self.metrics)

    @property
    def switches(self) -> int:
        # Only a direct transition from one process to a DIFFERENT process.
        return sum(a.pid is not None and b.pid is not None and a.pid != b.pid
                   for a, b in zip(self.timeline, self.timeline[1:]))


def read_processes(path: str | Path) -> list[Process]:
    result = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        fields = raw.partition("#")[0].split()
        if not fields:
            continue
        if len(fields) != 4:
            raise ValueError(f"{path}:{line_number}: expected PID arrival burst priority")
        try:
            result.append(Process(fields[0], *(int(x) for x in fields[1:])))
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: time and priority must be integers") from exc
    validate(result)
    return result


def validate(processes: list[Process]) -> None:
    if not processes:
        raise ValueError("At least one process is required")
    if len({p.pid for p in processes}) != len(processes):
        raise ValueError("PID values must be unique")
    for p in processes:
        if not p.pid or any(c.isspace() for c in p.pid):
            raise ValueError("PID must be a nonempty token")
        if any(type(x) is not int for x in (p.arrival, p.burst, p.priority)):
            raise ValueError("Time and priority must be integers")
        if p.arrival < 0 or p.burst <= 0:
            raise ValueError("arrival >= 0 and burst > 0 are required")


def simulate(processes: list[Process], algorithm: str, *, quantum: int = 2,
             aging_interval: int | None = None, quanta: tuple[int, ...] = (2, 4, 8),
             boost_interval: int = 20) -> Result:
    """Simulate FCFS, SJF, RR, SRTF, PRIORITY or MLFQ.

    Equal keys: earlier arrival, then input order. An equal key never preempts
    the running process. Arrivals at a quantum boundary precede requeueing.
    Aging uses cumulative ready-queue waiting, including waits after preemption.
    MLFQ higher-level preemption preserves the unused quantum. Global boosts
    occur at positive multiples of boost_interval and reset levels and budgets.
    """
    validate(processes)
    algorithm = algorithm.upper()
    if algorithm not in {"FCFS", "SJF", "RR", "SRTF", "PRIORITY", "MLFQ"}:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    if type(quantum) is not int or quantum <= 0:
        raise ValueError("quantum must be a positive integer")
    if aging_interval is not None and (type(aging_interval) is not int or aging_interval <= 0):
        raise ValueError("aging_interval must be a positive integer")
    if (len(quanta) != 3 or any(type(q) is not int or q <= 0 for q in quanta)
            or not quanta[0] < quanta[1] < quanta[2]):
        raise ValueError("MLFQ requires three strictly increasing positive integer quanta")
    if type(boost_interval) is not int or boost_interval <= 0:
        raise ValueError("boost_interval must be a positive integer")
    if aging_interval is not None and algorithm != "PRIORITY":
        raise ValueError("Aging is supported for PRIORITY only")

    n = len(processes)
    arrivals = sorted(range(n), key=lambda i: (processes[i].arrival, i))
    remaining = [p.burst for p in processes]
    starts: list[int | None] = [None] * n
    completions = [0] * n
    levels = [0] * n
    budgets = [quanta[0]] * n
    ready: list[int] = []
    queues: list[deque[int]] = [deque() for _ in range(3)]
    timeline: list[Segment] = []
    current: int | None = None
    pending: int | None = None
    cursor = t = done = dispatches = rr_budget = 0

    def segment(pid: str | None, end: int) -> None:
        if timeline and timeline[-1].pid == pid and timeline[-1].end == t:
            old = timeline[-1]
            timeline[-1] = Segment(old.start, end, pid)
        else:
            timeline.append(Segment(t, end, pid))

    def effective_priority(i: int) -> int:
        waited = t - processes[i].arrival - (processes[i].burst - remaining[i])
        return processes[i].priority - (waited // aging_interval if aging_interval else 0)

    while done < n:
        # First admit arrivals, then handle the process whose quantum just expired.
        while cursor < n and processes[arrivals[cursor]].arrival <= t:
            i = arrivals[cursor]
            (queues[0] if algorithm == "MLFQ" else ready).append(i)
            cursor += 1
        if pending is not None:
            if algorithm == "MLFQ":
                levels[pending] = min(2, levels[pending] + 1)
                budgets[pending] = quanta[levels[pending]]
                queues[levels[pending]].append(pending)
            else:
                ready.append(pending)
            pending = None

        if algorithm == "MLFQ":
            if t > 0 and t % boost_interval == 0:
                # Already-running task keeps its turn; queues preserve their FIFO order.
                waiting = [i for queue in queues for i in queue]
                for queue in queues:
                    queue.clear()
                queues[0].extend(waiting)
                for i in waiting + ([] if current is None else [current]):
                    levels[i], budgets[i] = 0, quanta[0]
            if current is not None and any(queues[level] for level in range(levels[current])):
                queues[levels[current]].appendleft(current)
                current = None
            if current is None:
                for queue in queues:
                    if queue:
                        current = queue.popleft()
                        dispatches += 1
                        break
        elif algorithm in {"SRTF", "PRIORITY"}:
            key = (lambda i: remaining[i]) if algorithm == "SRTF" else effective_priority
            if ready:
                best = min(ready, key=lambda i: (key(i), processes[i].arrival, i))
                if current is None or key(best) < key(current):
                    if current is not None:
                        ready.append(current)
                    ready.remove(best)
                    current = best
                    dispatches += 1
        elif current is None and ready:
            if algorithm == "SJF":
                current = min(ready, key=lambda i: (processes[i].burst, processes[i].arrival, i))
                ready.remove(current)
            else:
                current = ready.pop(0)
            rr_budget = quantum
            dispatches += 1

        if current is None:
            # Jump across idle time; a future global boost has no waiting tasks to affect.
            next_time = processes[arrivals[cursor]].arrival
            segment(None, next_time)
            t = next_time
            continue
        if starts[current] is None:
            starts[current] = t
        segment(processes[current].pid, t + 1)
        remaining[current] -= 1
        if algorithm == "RR":
            rr_budget -= 1
        elif algorithm == "MLFQ":
            budgets[current] -= 1
        t += 1
        if remaining[current] == 0:
            completions[current] = t
            done += 1
            current = None
        elif (algorithm == "RR" and rr_budget == 0) or (algorithm == "MLFQ" and budgets[current] == 0):
            pending, current = current, None

    metrics = []
    for i, p in enumerate(processes):
        assert starts[i] is not None
        turnaround = completions[i] - p.arrival
        metrics.append(Metrics(p.pid, p.arrival, p.burst, p.priority, starts[i], completions[i],
                               turnaround - p.burst, turnaround, starts[i] - p.arrival))
    label = algorithm
    if algorithm == "RR":
        label += f" q={quantum}"
    if aging_interval:
        label += f" aging={aging_interval}"
    if algorithm == "MLFQ":
        label += f" q={','.join(map(str, quanta))} boost={boost_interval}"
    return Result(label, list(processes), timeline, metrics, dispatches)
