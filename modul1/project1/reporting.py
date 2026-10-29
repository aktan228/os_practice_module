# Ответственные участники: Кабылбеков Айжигит (Б), Кашымбеков Актан (В)
"""Reproducible Russian report, CSV metrics and self-contained HTML/SVG."""
from __future__ import annotations

import csv
import hashlib
import html
import json
from dataclasses import asdict
from pathlib import Path

from scheduler import Result, read_processes, simulate
from verify_pr5 import verify as verify_pr5


def number(value):
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def color(pid):
    hue = int(hashlib.sha256(pid.encode()).hexdigest()[:8], 16) % 360
    return f"hsl({hue}, 58%, 76%)"


def gantt(result: Result, title: str):
    end = result.timeline[-1].end
    span = 40
    row_count = (end + span - 1) // span
    legend_rows = (len(result.processes) + 8) // 9
    height = 72 + row_count * 90 + legend_rows * 27
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="{height}" viewBox="0 0 1120 {height}" role="img" aria-label="{html.escape(title, quote=True)}">',
             '<rect width="100%" height="100%" fill="#fff"/>',
             '<g font-family="Arial,sans-serif" font-size="13" fill="#18283b">',
             f'<text x="24" y="28" font-size="19" font-weight="bold">{html.escape(title)}</text>']
    for row in range(row_count):
        lo, hi, y = row * span, min(end, (row + 1) * span), 52 + row * 90
        scale = 26
        for s in result.timeline:
            a, b = max(lo, s.start), min(hi, s.end)
            if b <= a:
                continue
            x, width = 40 + (a - lo) * scale, (b - a) * scale
            pid = s.pid if s.pid is not None else "IDLE"
            fill = color(pid) if s.pid is not None else "#e5e7eb"
            parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="32" fill="{fill}" stroke="#fff"><title>{html.escape(pid)}: [{s.start}, {s.end})</title></rect>')
            if width >= 38:
                parts.append(f'<text x="{x + width / 2}" y="{y + 21}" text-anchor="middle">{html.escape(pid)}</text>')
        ticks = set(range(lo, hi + 1, 5)) | {lo, hi}
        # Short FCFS schedules also label every process boundary for paper copying.
        if end <= span:
            ticks |= {s.start for s in result.timeline} | {s.end for s in result.timeline}
        for tick in sorted(ticks):
            x = 40 + (tick - lo) * scale
            parts.append(f'<path d="M{x},{y + 32}v6" stroke="#64748b"/><text x="{x}" y="{y + 56}" text-anchor="middle">{tick}</text>')
    for i, p in enumerate(result.processes):
        x, y = 34 + (i % 9) * 119, 62 + row_count * 90 + (i // 9) * 27
        parts.append(f'<rect x="{x}" y="{y - 13}" width="18" height="16" fill="{color(p.pid)}"/><text x="{x + 24}" y="{y}">{html.escape(p.pid)}</text>')
    parts.append('</g></svg>')
    return "\n".join(parts)


def rr_chart(results):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="620" viewBox="0 0 1120 620" role="img" aria-label="RR: квант и метрики">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g font-family="Arial,sans-serif" font-size="13" fill="#18283b">',
             '<text x="24" y="28" font-size="19" font-weight="bold">RR на mixed.txt: влияние кванта</text>']
    series = [("Среднее ожидание", [r.average("waiting") for r in results], "#2563eb"),
              ("Средний отклик", [r.average("response") for r in results], "#0f766e"),
              ("Переключения между процессами", [r.switches for r in results], "#b45309")]
    for index, (label, values, stroke) in enumerate(series):
        top, height = 70 + index * 180, 110
        maximum = max(values) * 1.15 or 1
        parts.append(f'<text x="32" y="{top - 12}" font-weight="bold">{label}</text>')
        for step in range(5):
            value = maximum * step / 4
            y = top + height - height * step / 4
            parts.append(f'<path d="M80,{y}H1060" stroke="#e2e8f0"/><text x="68" y="{y + 4}" text-anchor="end">{value:.1f}</text>')
        points = [(80 + i * 980 / 9, top + height - v / maximum * height) for i, v in enumerate(values)]
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{stroke}" stroke-width="3"/>')
        for i, (x, y) in enumerate(points):
            parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{stroke}"><title>q={i + 1}: {values[i]:.2f}</title></circle><text x="{x}" y="{top + height + 22}" text-anchor="middle">{i + 1}</text>')
    parts.append('<text x="1060" y="612" text-anchor="end">Квант q, единицы времени</text></g></svg>')
    return "\n".join(parts)


class Document:
    def __init__(self, output):
        self.output = output
        self.md = []
        self.html = []

    def heading(self, text, level=2):
        self.md.append(f"{'#' * level} {text}\n")
        self.html.append(f"<h{level}>{html.escape(text)}</h{level}>")

    def paragraph(self, text):
        self.md.append(text + "\n")
        self.html.append(f"<p>{html.escape(text)}</p>")

    def link(self, label, url):
        self.md.append(f"[{label}]({url})\n")
        self.html.append(f'<p><a href="{html.escape(url, quote=True)}">{html.escape(label)}</a></p>')

    def table(self, headers, rows):
        rows = [[number(cell) for cell in row] for row in rows]
        self.md += ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        self.md += ["| " + " | ".join(row) + " |" for row in rows]
        self.md.append("")
        self.html.append('<div class="table-wrap"><table><thead><tr>' + "".join(f"<th>{html.escape(x)}</th>" for x in headers) + "</tr></thead><tbody>" +
                         "".join("<tr>" + "".join(f"<td>{html.escape(x)}</td>" for x in row) + "</tr>" for row in rows) + "</tbody></table></div>")

    def image(self, name, title, source):
        (self.output / name).write_text(source, encoding="utf-8")
        self.md.append(f"![{title}]({name})\n")
        self.html.append(f'<figure>{source}<figcaption>{html.escape(title)}</figcaption></figure>')

    def save(self):
        (self.output / "report.md").write_text("\n".join(self.md), encoding="utf-8")
        style = """body{margin:0;background:#edf2f7;color:#18283b;font:16px/1.6 system-ui,Arial,sans-serif}main{max-width:1180px;margin:32px auto;padding:36px;background:white;border-radius:12px}h1{font-size:30px;line-height:1.2}h2{margin-top:40px;border-bottom:2px solid #dce5ee;padding-bottom:8px}h3{margin-top:28px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{border:1px solid #dce5ee;padding:8px 10px;text-align:right;white-space:nowrap}th{background:#eaf1f8}th:first-child,td:first-child{text-align:left}tbody tr:nth-child(even){background:#f7fafc}figure{margin:24px 0;overflow:auto}figure svg{max-width:100%;height:auto}figcaption{font-size:13px;color:#52677b}p{max-width:1050px}.actions{margin:0 0 24px}button{padding:8px 18px;border:0;border-radius:6px;background:#1d4ed8;color:white;cursor:pointer}@media print{body{background:white}main{margin:0;padding:0}h2{break-after:avoid}tr,figure{break-inside:avoid}table{font-size:10px}th,td{padding:4px}.actions{display:none}}"""
        page = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Проект 1 — А, Б, В</title><style>' + style + '</style><main><div class="actions"><button onclick="window.print()">Печать / сохранить PDF</button></div>' + "\n".join(self.html) + '</main></html>'
        (self.output / "report.html").write_text(page, encoding="utf-8")


def summary_row(r):
    return [r.algorithm, r.average("waiting"), r.average("turnaround"), r.average("response"), r.switches]


SUMMARY_HEADERS = ["Алгоритм", "Среднее ожидание", "Средний оборот", "Средний отклик", "Переключения"]


def save_run(output, stem, result):
    write_csv(output / f"{stem}_metrics.csv", (asdict(m) for m in result.metrics))
    write_csv(output / f"{stem}_timeline.csv", (asdict(s) for s in result.timeline))


def control_check(processes):
    """Independent hand-derived values, NOT a supplied PR-5 answer key."""
    signature = [(p.pid, p.arrival, p.burst, p.priority) for p in processes]
    if signature != [("P1", 0, 8, 2), ("P2", 1, 4, 3), ("P3", 2, 9, 1), ("P4", 3, 5, 4)]:
        return None
    expected = {"FCFS": ([0, 8, 12, 21], [8, 12, 21, 26], [0, 7, 10, 18]),
                "SJF": ([0, 8, 17, 12], [8, 12, 26, 17], [0, 7, 15, 9]),
                "RR": ([0, 2, 4, 8], [22, 12, 26, 23], [14, 7, 15, 15])}
    rows = []
    for algorithm, (starts, completions, waits) in expected.items():
        r = simulate(processes, algorithm)
        passed = ([m.start for m in r.metrics] == starts and [m.completion for m in r.metrics] == completions
                  and [m.waiting for m in r.metrics] == waits)
        if not passed:
            raise AssertionError(f"Control mismatch for {algorithm}")
        rows.append([r.algorithm, sum(waits) / 4, r.average("waiting"), r.average("turnaround"), "PASS"])
    return rows


def generate(input_dir: Path, output: Path, *, aging_interval=3, quanta=(2, 4, 8), boost_interval=20):
    datasets = {name: read_processes(input_dir / f"{name}.txt") for name in ("set1", "jobs", "mixed", "starve")}
    output.mkdir(parents=True, exist_ok=True)
    algorithms = ["FCFS", "SJF", "RR", "SRTF", "PRIORITY"]
    runs = {name: [simulate(ps, a) for a in algorithms] for name, ps in datasets.items()}
    sweep = [simulate(datasets["mixed"], "RR", quantum=q) for q in range(1, 11)]
    aged = simulate(datasets["starve"], "PRIORITY", aging_interval=aging_interval)
    mlfq = simulate(datasets["mixed"], "MLFQ", quanta=quanta, boost_interval=boost_interval)
    for name, results in runs.items():
        for a, r in zip(algorithms, results):
            save_run(output, f"{name}_{a.lower()}", r)
        write_csv(output / f"{name}_summary.csv", (dict(zip(["algorithm", "avg_waiting", "avg_turnaround", "avg_response", "switches"], summary_row(r))) for r in results))
    for q, r in enumerate(sweep, 1):
        save_run(output, f"mixed_rr_q{q}", r)
    save_run(output, "starve_priority_aging", aged)
    save_run(output, "mixed_mlfq", mlfq)
    write_csv(output / "rr_quantums.csv", ({"quantum": q, "avg_waiting": r.average("waiting"),
               "avg_turnaround": r.average("turnaround"), "avg_response": r.average("response"),
               "switches": r.switches, "dispatches": r.dispatches} for q, r in enumerate(sweep, 1)))
    checks = control_check(datasets["set1"])
    external = verify_pr5(input_dir, output)
    (output / "manifest.json").write_text(json.dumps({"input_sha256": {name + ".txt": hashlib.sha256((input_dir / (name + ".txt")).read_bytes()).hexdigest() for name in datasets},
        "rr_default_quantum": 2, "aging_interval": aging_interval, "mlfq_quanta": quanta,
        "mlfq_boost_interval": boost_interval, "pr5_reference_supplied": True,
        "pr5_repository_verified": True, "pr5_reference_commit": external["commit"],
        "pr5_published_checks_passed": external["published_passed"],
        "pr5_differential_checks_passed": external["differential_passed"],
        "pr5_teacher_original_verified": False,
        "hand_control_passed": checks is not None}, ensure_ascii=False, indent=2), encoding="utf-8")

    doc = Document(output)
    doc.heading("Проект 1. Планировщик учебного сервера — блоки А, Б и В", 1)
    doc.paragraph("Расчёты выполнены на исходных set1.txt, jobs.txt, mixed.txt и starve.txt. Программа моделирует один процессор; все времена — условные целые единицы. Стоимость переключения равна нулю. Исходные данные не изменяются.")
    doc.heading("Модель, формулы и правила")
    doc.paragraph("arrival — время поступления; burst — требуемое время CPU; start — первое выполнение; completion — завершение. Оборот T = completion − arrival. Ожидание W = T − burst. Отклик R = start − arrival. Ожидание включает все паузы после вытеснения. Средние берутся по всем процессам, без округления промежуточных значений.")
    doc.paragraph("Меньшее число означает более высокий приоритет. При равенстве ключей выбирается более раннее поступление, затем порядок строк в файле. При равенстве оставшегося времени или приоритета работающий процесс не вытесняется. SJF невытесняющий; SRTF и Priority вытесняющие. В RR новые поступления в момент окончания кванта помещаются в очередь перед возвращаемым процессом; ожидающие сохраняют FIFO-порядок.")
    doc.paragraph("Переключение — непосредственный переход от одного PID к другому. Первый запуск, переходы через простой и повторная выдача CPU тому же PID не считаются переключениями. Число выдач CPU (dispatches) отдельно записано в rr_quantums.csv. Правила сверены с ПР-5 в указанном пользователем репозитории: равенство ключей, граница кванта RR, накопление ожидания для старения и подсчёт переключений совпадают. Опубликованные результаты репозитория проверены отдельно от отсутствующего оригинала задания преподавателя.")

    doc.heading("А. Базовый блок")
    fcfs = runs["jobs"][0]
    doc.heading("А1. FCFS для jobs.txt: диаграмма и ручной расчёт", 3)
    doc.image("jobs_fcfs_gantt.svg", "FCFS на jobs.txt — образец для переноса на бумагу", gantt(fcfs, "jobs.txt — FCFS"))
    doc.table(["PID", "Приход", "CPU", "Первый старт", "Конец", "Ожидание", "Оборот"],
              [[m.pid, m.arrival, m.burst, m.start, m.completion, m.waiting, m.turnaround] for m in fcfs.metrics])
    doc.paragraph("Ручной способ: start первого процесса = arrival; start следующего = max(его arrival, completion предыдущего); completion = start + burst. Например, P2: start = max(2, 7) = 7, completion = 11, W = 7 − 2 = 5, T = 11 − 2 = 9.")
    doc.paragraph(f"Среднее ожидание FCFS: ({' + '.join(str(m.waiting) for m in fcfs.metrics)}) / {len(fcfs.metrics)} = {fcfs.average('waiting'):.2f}. Средний оборот = {fcfs.average('turnaround'):.2f}.")
    doc.paragraph("Требование о бумаге: перерисуйте диаграмму, расчёты и таблицу от руки, сфотографируйте и сохраните assets/fcfs_jobs_handwritten.jpg. Добавьте фото в README.md указанной там Markdown-строкой. Электронная диаграмма не заменяет требуемое фото; это единственная физическая часть задания, которую программа не выполняет.")
    doc.heading("А2–А4. Сравнение FCFS, SJF, RR q=2 и самопроверка", 3)
    doc.table(SUMMARY_HEADERS, [summary_row(r) for r in runs["jobs"][:3]])
    best = min(runs["jobs"][:3], key=lambda r: r.average("waiting"))
    doc.paragraph(f"Из трёх базовых алгоритмов для jobs.txt лучший по среднему ожиданию и обороту — {best.algorithm}: {best.average('waiting'):.2f} и {best.average('turnaround'):.2f}. Он выбирает короткие задачи после завершения текущей. RR q=2 быстрее даёт первый отклик ({runs['jobs'][2].average('response'):.2f}), но повышает среднее ожидание. Поэтому слово «лучший» зависит от выбранной метрики.")
    if checks is not None:
        doc.table(["set1: алгоритм", "Ожидание вручную", "Ожидание программы", "Оборот программы", "Проверка"], checks)
        doc.paragraph("PASS в этой таблице означает совпадение первых запусков, завершений и ожиданий каждого процесса с независимо рассчитанными контрольными значениями в reporting.py и тестах. Дополнительная внешняя сверка с опубликованными результатами ПР-5 приведена ниже.")
    else:
        doc.paragraph("Состав set1.txt отличается от встроенного ручного примера: контроль с ним пропущен. Результаты расчёта сохранены; для проверки нужен соответствующий внешний эталон.")
    for r in runs["jobs"][1:3]:
        doc.image(f"jobs_{r.algorithm.split()[0].lower()}_gantt.svg", r.algorithm + " на jobs.txt", gantt(r, "jobs.txt — " + r.algorithm))

    doc.heading("А3. Внешняя сверка с ПР-5 из GitHub", 3)
    doc.paragraph(f"Проверен снимок aktan228/operation_system_practice_tasks, commit {external['commit']}, дата проверки {external['verified_on']}. Исходные файлы снимка сохранены в reference/pr5, их Git blob SHA проверяются перед каждым запуском сверки. Все {external['published_passed']} опубликованных расписаний и метрик совпали; дополнительно совпали {external['differential_passed']} расписания на четырёх исходных наборах проекта.")
    doc.link("Источник: ПР-5, README и опубликованные результаты", f"{external['repository']}/tree/{external['commit']}/pr5")
    doc.table(["Проверка опубликованного результата", "Вход", "Ожидание", "Оборот", "Отклик", "Статус"],
              [[r['algorithm'], "set1 проекта" if 'local' in r['input'] else "set1 репозитория", r['avg_waiting'], r['avg_turnaround'], r['avg_response'], r['status']] for r in external['published_checks']])
    doc.paragraph("У set1 в обоих источниках одинаковые PID, arrival и burst, но приоритеты разные: в проекте [2, 3, 1, 4], в ПР-5 [3, 1, 4, 2]. Поэтому FCFS, SJF, SRTF и RR сопоставляются на set1 проекта, а опубликованный Priority проверен на set1 репозитория. Приоритеты исходного файла проекта сохранены; его результат Priority закономерно отличается и не объявляется ошибкой.")
    doc.paragraph("Опубликованный RR использует q=3: ожидание 13,50, оборот 20,00, отклик 3,00. Для задания проекта используется q=2: ожидание 12,75, оборот 19,25, отклик 2,00 на set1. RR q=2 дополнительно проверен против реализации simulate из ПР-5 в числе 64 сопоставлений. Нельзя сравнивать значения RR при разных квантах как один контрольный пример.")
    doc.paragraph("README репозитория сообщает о противоречии в исходном эталоне FCFS: 9,25 и 15,75 вместо 8,75 и 15,25. Наш ручной расчёт и опубликованное расписание подтверждают 8,75 и 15,25. Сам оригинал преподавательского условия по ссылке не найден, поэтому его проверка отдельно не заявляется.")
    issue = external['full_upstream_source_issue']
    if issue:
        doc.paragraph(f"Важное ограничение проверки: полный sched.py из репозитория содержит SyntaxError в строке {issue['line']} — постороннее alidate перед ключом turnaround. Полный внешний скрипт и его тесты не объявляются успешно запущенными. Для 64 сопоставлений загружается только просмотренная неизменённая часть исходника до функции metrics: определения Process, validate и simulate. Исходник в снимке не исправляется. Пять сохранённых результатов дополнительно проверены независимо от этой загрузки.")
    doc.paragraph("В 64 сопоставления входят четыре набора × 16 вариантов: FCFS, SJF, SRTF, Priority без старения, Priority со старением 2 и 3, RR с квантами 1…10. Сравнивается полная последовательность выполнения, при этом соседние интервалы одного PID объединяются, а IDLE приводится к одному обозначению. MLFQ в ПР-5 отсутствует и проверяется собственными тестами проекта.")

    doc.heading("Б. Основной блок")
    doc.heading("Б1. Пять алгоритмов на jobs.txt", 3)
    doc.table(SUMMARY_HEADERS, [summary_row(r) for r in runs["jobs"]])
    doc.heading("Б2. Пять алгоритмов на mixed.txt", 3)
    doc.table(SUMMARY_HEADERS, [summary_row(r) for r in runs["mixed"]])
    doc.paragraph("В mixed.txt короткими считаем процессы burst ≤ 4, длинными — burst > 4: в исходном файле это 15 и 3 процесса соответственно. Общая средняя может скрывать задержки коротких запросов, поэтому ниже приведена отдельная оценка их отклика и ожидания.")
    doc.table(["Алгоритм", "Отклик коротких", "Ожидание коротких", "Последнее завершение длинных"],
              [[r.algorithm, sum(m.response for m in r.metrics if m.burst <= 4) / sum(m.burst <= 4 for m in r.metrics),
                sum(m.waiting for m in r.metrics if m.burst <= 4) / sum(m.burst <= 4 for m in r.metrics),
                max(m.completion for m in r.metrics if m.burst > 4)] for r in runs["mixed"]])
    doc.heading("Б3. RR: кванты 1…10 на mixed.txt", 3)
    doc.table(["Квант", "Среднее ожидание", "Средний отклик", "Переключения"],
              [[q, r.average("waiting"), r.average("response"), r.switches] for q, r in enumerate(sweep, 1)])
    doc.image("rr_quantums.svg", "Квант RR и три метрики (раздельные шкалы)", rr_chart(sweep))
    doc.heading("Б4. Рекомендация заказчику", 3)
    srtf = runs["mixed"][3]
    doc.paragraph(f"Если длительности burst заранее известны, на этом наборе рекомендован SRTF: ожидание {srtf.average('waiting'):.2f}, оборот {srtf.average('turnaround'):.2f}; средний отклик коротких запросов {sum(m.response for m in srtf.metrics if m.burst <= 4) / sum(m.burst <= 4 for m in srtf.metrics):.2f}. Квант SRTF не нужен. Все три длинных процесса в конечном наборе завершаются, но при бесконечном потоке коротких задач SRTF сам по себе не гарантирует отсутствие голодания.")
    doc.paragraph(f"Если выбирать RR, q=1 даёт минимальные в эксперименте ожидание {sweep[0].average('waiting'):.2f} и отклик {sweep[0].average('response'):.2f}, ценой {sweep[0].switches} переключений. Практический компромисс — q=2: ожидание {sweep[1].average('waiting'):.2f}, отклик {sweep[1].average('response'):.2f}, {sweep[1].switches} переключений (на {100 * (1 - sweep[1].switches / sweep[0].switches):.1f}% меньше). При нулевой цене переключений q=1 выигрывает по указанным временам; выбор q=2 мотивирован уменьшением количества переключений, а не доказанным минимумом суммарных затрат. Для выбора реального кванта нужно измерить стоимость переключения.")
    for a, r in zip(algorithms, runs["mixed"]):
        doc.image(f"mixed_{a.lower()}_gantt.svg", r.algorithm + " на mixed.txt", gantt(r, "mixed.txt — " + r.algorithm))

    doc.heading("В. Продвинутый блок")
    plain = runs["starve"][4]
    plain_p1 = next(m for m in plain.metrics if m.pid == "P1")
    aged_p1 = next(m for m in aged.metrics if m.pid == "P1")
    doc.heading("В1–В2. Голодание P1 и старение приоритета", 3)
    doc.paragraph(f"Без старения P1 имеет приоритет 9 и уступает всем остальным процессам. Его первое выполнение — t={plain_p1.start}, завершение — t={plain_p1.completion}; ожидание {plain_p1.waiting}. Поток в файле конечный, поэтому это длительное откладывание, демонстрирующее механизм голодания, а не бесконечное ожидание. При непрерывном поступлении задач с более высоким приоритетом ожидание могло бы стать неограниченным.")
    doc.paragraph(f"Старение: effective_priority = base_priority − floor(total_ready_wait / {aging_interval}), где total_ready_wait = t − arrival − executed. Учитывается только накопленное ожидание, включая паузы после вытеснения; работающий процесс не накапливает ожидание и сохраняет полученное улучшение. Снизу приоритет не ограничен. При строгом улучшении ключа возможны вытеснения; при равенстве текущий процесс продолжает работу.")
    doc.table(["Вариант", "Старт P1", "Конец P1", "Ожидание P1", "Оборот P1", "Отклик P1"],
              [[label, m.start, m.completion, m.waiting, m.turnaround, m.response]
               for label, m in [("Priority", plain_p1), (f"Priority + aging/{aging_interval}", aged_p1)]])
    doc.paragraph(f"Со старением P1 запускается на {plain_p1.start - aged_p1.start} единиц раньше и завершается на {plain_p1.completion - aged_p1.completion} единиц раньше. Все 20 процессов завершаются в обоих вариантах.")
    doc.table(SUMMARY_HEADERS, [summary_row(plain), summary_row(aged)])
    doc.image("starve_priority_gantt.svg", "Priority без старения", gantt(plain, "starve.txt — Priority"))
    doc.image("starve_aging_gantt.svg", "Priority со старением", gantt(aged, "starve.txt — " + aged.algorithm))
    doc.heading("В3. MLFQ: три уровня и периодический boost", 3)
    doc.paragraph(f"Используются очереди Q0, Q1, Q2, кванты {quanta[0]}, {quanta[1]}, {quanta[2]}. Новая задача поступает в Q0. Выбирается самая высокая непустая очередь, внутри — FIFO. Исчерпание кванта понижает задачу на один уровень; из Q2 она возвращается в Q2. Поступление в более высокую очередь вытесняет задачу, сохраняя остаток её кванта и место в начале своей очереди.")
    doc.paragraph(f"Каждые {boost_interval} единиц времени все незавершённые поступившие задачи поднимаются в Q0, бюджеты квантов сбрасываются. Работающая задача продолжает свой ход и получает новый квант Q0; ожидающие упорядочиваются по прежним уровням сверху вниз и FIFO внутри уровня. В точке события порядок такой: поступления, возврат после кванта, boost, выбор процесса. Эта конкретизация устраняет неоднозначности при одновременных событиях.")
    compare = [runs["mixed"][3], runs["mixed"][2], mlfq]
    doc.table(SUMMARY_HEADERS, [summary_row(r) for r in compare])
    doc.table(["Алгоритм", "Отклик коротких", "Максимальный отклик", "Последнее завершение длинных"],
              [[r.algorithm, sum(m.response for m in r.metrics if m.burst <= 4) / sum(m.burst <= 4 for m in r.metrics),
                max(m.response for m in r.metrics), max(m.completion for m in r.metrics if m.burst > 4)] for r in compare])
    doc.image("mixed_mlfq_gantt.svg", "MLFQ на mixed.txt", gantt(mlfq, "mixed.txt — " + mlfq.algorithm))
    doc.heading("В4. Почему MLFQ не требует знания длительности", 3)
    doc.paragraph("MLFQ принимает решения по наблюдаемому поведению: исчерпала ли задача квант, на каком она уровне, сколько бюджета осталось и наступил ли boost. Полная длительность burst и remaining не участвуют в выборе очереди. Симулятор хранит remaining только для фиксации факта завершения — это аналог сигнала о завершении процесса от системы. Короткие задачи успевают закончиться в верхних очередях, длительные постепенно уходят ниже; boost возвращает давно ожидающие задачи наверх.")
    doc.paragraph(f"Для сервера с неизвестными длительностями рекомендована проверенная конфигурация MLFQ ({quanta[0]}/{quanta[1]}/{quanta[2]}, boost {boost_interval}). На mixed.txt её средний отклик {mlfq.average('response'):.2f}, против {runs['mixed'][2].average('response'):.2f} у RR q=2; переключений {mlfq.switches} против {runs['mixed'][2].switches}. Все длинные задачи завершаются. Это результат конкретного опыта, а не доказательство оптимальности параметров или гарантия при произвольной перегрузке.")
    doc.heading("Файлы результатов и воспроизводимость")
    doc.paragraph("Для каждого алгоритма и набора сохранены *_metrics.csv (метрики каждого PID) и *_timeline.csv (непрерывные интервалы [start, end)). Есть сводные CSV, rr_quantums.csv и SVG-диаграммы. manifest.json содержит параметры, SHA-256 исходных файлов и статус внешней сверки. pr5_verification.json и pr5_*_checks.csv содержат подробные результаты сопоставлений. report.html автономен: таблицы и SVG встроены, подключение к сети не требуется. Команды запуска и проверки приведены в README.md проекта.")
    doc.save()
    return {"jobs": runs["jobs"], "mixed": runs["mixed"], "plain_p1": plain_p1, "aged_p1": aged_p1}
