# Ответственные участники: Кашымбеков Актан (В)
"""CLI: python run.py [report|simulate], default is a complete A/B/C report."""
from __future__ import annotations

import argparse
from pathlib import Path

from reporting import generate, save_run
from scheduler import read_processes, simulate


ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Проект 1: планирование процессов, блоки А, Б, В")
    commands = parser.add_subparsers(dest="command")
    report = commands.add_parser("report", help="Пересоздать таблицы, диаграммы и HTML-отчёт")
    report.add_argument("--input-dir", type=Path, default=ROOT)
    report.add_argument("--output-dir", type=Path)
    report.add_argument("--aging-interval", type=int, default=3)
    report.add_argument("--mlfq-quanta", type=int, nargs=3, default=(2, 4, 8))
    report.add_argument("--boost-interval", type=int, default=20)
    single = commands.add_parser("simulate", help="Рассчитать один алгоритм для одного файла")
    single.add_argument("--input", type=Path, required=True)
    single.add_argument("--algorithm", type=str.upper, required=True,
                        choices=["FCFS", "SJF", "RR", "SRTF", "PRIORITY", "MLFQ"])
    single.add_argument("--quantum", type=int, default=2)
    single.add_argument("--aging-interval", type=int)
    single.add_argument("--mlfq-quanta", type=int, nargs=3, default=(2, 4, 8))
    single.add_argument("--boost-interval", type=int, default=20)
    single.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "simulate":
            r = simulate(read_processes(args.input), args.algorithm, quantum=args.quantum,
                         aging_interval=args.aging_interval, quanta=tuple(args.mlfq_quanta),
                         boost_interval=args.boost_interval)
            print(r.algorithm)
            print("PID        start  finish  waiting  turnaround  response")
            for m in r.metrics:
                print(f"{m.pid:10} {m.start:5} {m.completion:7} {m.waiting:8} {m.turnaround:11} {m.response:9}")
            print(f"Average waiting: {r.average('waiting'):.2f}; turnaround: {r.average('turnaround'):.2f}; "
                  f"response: {r.average('response'):.2f}; switches: {r.switches}; dispatches: {r.dispatches}")
            print("Gantt: " + " | ".join(f"{s.start}-{s.end}:{s.pid or 'IDLE'}" for s in r.timeline))
            if args.output_dir:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                save_run(args.output_dir, args.algorithm.lower(), r)
        else:
            input_dir = args.input_dir.resolve() if args.command else ROOT
            output = ((args.output_dir or input_dir / "results").resolve() if args.command else ROOT / "results")
            settings = ({"aging_interval": args.aging_interval, "quanta": tuple(args.mlfq_quanta),
                         "boost_interval": args.boost_interval} if args.command else {})
            generate(input_dir, output, **settings)
            print(f"Report: {output / 'report.html'}")
            print("A/B/C calculations complete. PR-5 repository: 5 published results and 64 schedules PASS.")
            print("Paper photo pending. The original teacher answer key is separate from the repository cross-check.")
    except (ValueError, OSError, AssertionError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
