# Ответственные участники: Кашымбеков Актан (В), Кабылбеков Айжигит (Б)
"""Verify local schedules against the pinned PR-5 repository snapshot.

The full upstream sched.py has a syntax error in metrics(). Its unchanged,
reviewed prefix contains imports, Process, validation and simulate; only this
prefix is loaded for differential tests. Published result files are checked
separately, including every process metric. No upstream file is modified.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import sys
import types
from pathlib import Path

from scheduler import read_processes, simulate


ROOT = Path(__file__).resolve().parent


def normalize(intervals):
    result = []
    for start, end, pid in intervals:
        pid = None if pid == "IDLE" else pid
        if result and result[-1][2] == pid and result[-1][1] == start:
            result[-1] = (result[-1][0], end, pid)
        else:
            result.append((start, end, pid))
    return result


def parse_published(path):
    text = path.read_text(encoding="utf-8")
    timeline = [(int(a), int(b), pid) for a, b, pid in re.findall(r"(\d+)-(\d+):([^\s|]+)", text.splitlines()[0])]
    rows = {}
    names = ["arrival", "burst", "priority", "start", "completion", "waiting", "turnaround", "response"]
    for line in text.splitlines()[2:]:
        fields = line.split()
        if len(fields) == 9 and all(re.fullmatch(r"-?\d+", v) for v in fields[1:]):
            rows[fields[0]] = dict(zip(names, map(int, fields[1:])))
    if not timeline or not rows:
        raise ValueError(f"Cannot parse published result: {path}")
    return timeline, rows


def verify(root=ROOT, output=None):
    root = Path(root)
    reference = ROOT / "reference"
    manifest = json.loads((reference / "SOURCE.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        content = (reference / entry["path"]).read_bytes()
        blob_sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob_sha != entry["blob_sha"]:
            raise AssertionError(f"Reference integrity failure: {entry['path']}")

    local = read_processes(root / "set1.txt")
    remote = read_processes(reference / "pr5/set1.txt")
    if [(p.pid, p.arrival, p.burst) for p in local] != [(p.pid, p.arrival, p.burst) for p in remote]:
        raise ValueError("Local set1 arrival/burst differs from the pinned PR-5 example")

    published = []
    for algorithm in ("FCFS", "SJF", "SRTF", "RR", "PRIORITY"):
        # Priority must use the repository priorities; the other four ignore them.
        processes = remote if algorithm == "PRIORITY" else local
        result = simulate(processes, algorithm, quantum=3)
        expected_trace, expected_rows = parse_published(reference / f"pr5/results/set1_{algorithm.lower()}.txt")
        actual_trace = [(s.start, s.end, s.pid) for s in result.timeline]
        if normalize(actual_trace) != normalize(expected_trace):
            raise AssertionError(f"Published timeline mismatch: {algorithm}")
        if {m.pid for m in result.metrics} != set(expected_rows):
            raise AssertionError(f"Published PID mismatch: {algorithm}")
        for m in result.metrics:
            for field, expected in expected_rows[m.pid].items():
                if field == "priority" and algorithm != "PRIORITY":
                    continue
                if getattr(m, field) != expected:
                    raise AssertionError(f"Published metric mismatch: {algorithm}/{m.pid}/{field}")
        published.append({"algorithm": result.algorithm,
                          "input": "repository set1" if algorithm == "PRIORITY" else "local set1 (same arrival/burst)",
                          "avg_waiting": result.average("waiting"), "avg_turnaround": result.average("turnaround"),
                          "avg_response": result.average("response"), "status": "PASS"})

    source = (reference / "pr5/sched.py").read_text(encoding="utf-8")
    source_issue = None
    try:
        ast.parse(source)
    except SyntaxError as exc:
        source_issue = {"type": "SyntaxError", "line": exc.lineno, "message": exc.msg,
                        "source_line": (exc.text or "").strip()}
    prefix = source.split("\ndef metrics(", 1)[0]
    if prefix == source:
        raise ValueError("Reference simulate/metrics boundary not found")
    ast.parse(prefix)
    # The snapshot prefix was inspected before use. It has definitions and stdlib
    # imports only, and it does not call a CLI, write files or access the network.
    module_name = "_verified_pr5_simulation"
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    try:
        exec(compile(prefix, str(reference / "pr5/sched.py") + " [prefix only]", "exec"), module.__dict__)
        differential = []
        variants = [(a, {}) for a in ("FCFS", "SJF", "SRTF", "PRIORITY")]
        variants += [("PRIORITY", {"aging_interval": a}) for a in (2, 3)]
        variants += [("RR", {"quantum": q}) for q in range(1, 11)]
        for name in ("set1", "jobs", "mixed", "starve"):
            processes = read_processes(root / f"{name}.txt")
            upstream_processes = [module.Process(p.pid, p.arrival, p.burst, p.priority) for p in processes]
            for algorithm, params in variants:
                result = simulate(processes, algorithm, **params)
                upstream_params = {"quantum": params.get("quantum", 2), "aging": params.get("aging_interval", 0)}
                expected = module.simulate(upstream_processes, algorithm.lower(), **upstream_params)
                actual = [(s.start, s.end, s.pid) for s in result.timeline]
                if normalize(actual) != normalize(expected):
                    raise AssertionError(f"Differential mismatch: {name}/{result.algorithm}")
                differential.append({"dataset": name, "algorithm": result.algorithm, "status": "PASS"})
    finally:
        sys.modules.pop(module_name, None)

    local_priority = simulate(local, "PRIORITY")
    data = {"status": "PASS", "repository": manifest["repository"], "commit": manifest["commit"],
            "verified_on": manifest["verified_on"], "reference_files_integrity": "PASS",
            "published_checks": published, "published_passed": len(published),
            "differential_checks": differential, "differential_passed": len(differential),
            "full_upstream_source_issue": source_issue,
            "upstream_execution_scope": "Unmodified source prefix before def metrics; full script not executed",
            "local_priorities": [p.priority for p in local], "repository_priorities": [p.priority for p in remote],
            "local_priority_averages": {field: local_priority.average(field) for field in ("waiting", "turnaround", "response")},
            "rr_project_quantum": 2, "rr_published_quantum": 3,
            "teacher_original_reference_verified": False}
    if output is not None:
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "pr5_verification.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        for name, rows in (("pr5_published_checks.csv", published), ("pr5_differential_checks.csv", differential)):
            with (output / name).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    return data


if __name__ == "__main__":
    result = verify(output=ROOT / "results")
    print(f"PR-5 repository commit: {result['commit']}")
    print(f"Published results: {result['published_passed']}/5 PASS")
    print(f"Differential schedules: {result['differential_passed']}/64 PASS")
    print("Note: full upstream source contains a syntax error; unchanged simulation prefix checked separately.")
    print("Repository cross-check passed; original teacher answer key and paper photo remain separate requirements.")
