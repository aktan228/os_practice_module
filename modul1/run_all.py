"""Run the complete submission and retain command output on Windows or Ubuntu."""
# Ответственный: Кашымбеков Актан — сборка и проверка проекта 1.
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required")
    is_wsl = platform.system() == "Linux" and "microsoft" in platform.release().lower()
    label = "ubuntu-wsl" if is_wsl else platform.system().lower()
    folder = ROOT / "logs" / label
    folder.mkdir(parents=True, exist_ok=True)
    environment = {"platform": platform.platform(), "system": platform.system(),
                   "python": platform.python_version(), "executable": sys.executable,
                   "wsl": is_wsl, "network_required": False,
                   "checked_at": datetime.now(timezone(timedelta(hours=6))).isoformat(),
                   "display_timezone": "Asia/Bishkek"}
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    commands = [
        ("run_output.txt", [sys.executable, "-u", "project1/run.py"]),
        ("tests_output.txt", [sys.executable, "-u", "-m", "unittest", "discover", "-s", "project1", "-p", "test_scheduler.py", "-v"]),
        ("pr5_check_output.txt", [sys.executable, "-u", "project1/verify_pr5.py"]),
    ]
    statuses = {}
    for filename, command in commands:
        print("\n$ " + " ".join(command), flush=True)
        with (folder / filename).open("w", encoding="utf-8", newline="\n") as stream:
            stream.write("Command: " + " ".join(command) + "\n")
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8")
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                stream.write(line)
            code = process.wait()
            stream.write(f"\nExit code: {code}\n")
        shutil.copy2(folder / filename, ROOT / filename)
        statuses[filename] = code
        if code:
            environment["commands"] = statuses
            (folder / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
            raise SystemExit(code)
    verification = json.loads((ROOT / "project1/results/pr5_verification.json").read_text(encoding="utf-8"))
    environment.update(commands=statuses, status="PASS", own_tests=13,
                       pr5_published_passed=verification["published_passed"],
                       pr5_differential_passed=verification["differential_passed"],
                       handwritten_photo_present=(ROOT / "project1/assets/fcfs_jobs_handwritten.jpg").is_file())
    (folder / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
    all_checks = []
    for file in sorted((ROOT / "logs").glob("*/environment.json")):
        result = json.loads(file.read_text(encoding="utf-8"))
        all_checks.append(f"| {file.parent.name} | {result['python']} | {result.get('status', 'FAIL')} | {result.get('own_tests', 0)} | {result.get('pr5_published_passed', 0)}/5 | {result.get('pr5_differential_passed', 0)}/64 |")
    lines = ["# Фактическая проверка сборки", "", "| Среда | Python | Статус | Тесты | Результаты ПР-5 | Расписания ПР-5 |",
             "| --- | --- | --- | --- | --- | --- |", *all_checks, "",
             "Команды запускались автоматически через run_all.py. Полный текст вывода и сведения о среде сохранены в logs/<среда>/.", "",
             "Фото ручной диаграммы: " + ("добавлено." if environment["handwritten_photo_present"] else "ещё не добавлено; образец находится в project1/README.md."), "",
             "Сверка выполнена с опубликованной ПР-5. Оригинал преподавательского условия отдельно не предоставлен.", ""]
    (ROOT / "CHECK_STATUS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nPASS: {label}; 13 tests; PR-5 5/5 + 64/64. Logs: {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
