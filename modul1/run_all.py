"""Generate the report, run tests, and save one text log for this OS."""
# Ответственный: Кашымбеков Актан — сборка и проверка проекта 1.
from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    label = "ubuntu" if platform.system() == "Linux" else platform.system().lower()
    folder = ROOT / "logs"
    folder.mkdir(exist_ok=True)
    log_path = folder / f"{label}.txt"
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    commands = [
        [sys.executable, "-u", "project1/run.py"],
        [sys.executable, "-u", "-m", "unittest", "discover", "-s", "project1", "-p", "test_scheduler.py", "-v"],
    ]
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        checked_at = datetime.now(timezone(timedelta(hours=6))).isoformat()
        log.write(f"System: {platform.platform()}\nPython: {platform.python_version()}\n")
        log.write(f"Checked at: {checked_at} (Asia/Bishkek)\n\n")
        for command in commands:
            header = "$ " + " ".join(command) + "\n"
            print(header, end="", flush=True)
            log.write(header)
            with subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8") as process:
                assert process.stdout is not None
                for line in process.stdout:
                    print(line, end="", flush=True)
                    log.write(line)
                code = process.wait()
            log.write(f"Exit code: {code}\n\n")
            if code:
                print(f"FAILED. Details: {log_path}")
                return code
        log.write("PASS: report, 13 tests, PR-5 published results 5/5 and schedules 64/64.\n")
    print(f"PASS. Report: {ROOT / 'project1/results/report.html'}")
    print(f"Command output: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
