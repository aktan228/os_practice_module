# Ответственные участники: Осмонов Медер (А), Адылов Арсен (Б), Кашымбеков Актан (В)
"""Hand-computed examples, boundary cases, and independent timeline invariants."""
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scheduler import Process, read_processes, simulate


def trace(result):
    return [(s.start, s.end, s.pid) for s in result.timeline]


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.control = [Process("P1", 0, 8, 2), Process("P2", 1, 4, 3),
                        Process("P3", 2, 9, 1), Process("P4", 3, 5, 4)]

    def test_fcfs_hand_calculation(self):
        r = simulate(self.control, "FCFS")
        self.assertEqual(trace(r), [(0, 8, "P1"), (8, 12, "P2"), (12, 21, "P3"), (21, 26, "P4")])
        self.assertEqual([m.waiting for m in r.metrics], [0, 7, 10, 18])
        self.assertEqual(r.average("turnaround"), 15.25)

    def test_sjf_hand_calculation(self):
        r = simulate(self.control, "SJF")
        self.assertEqual(trace(r), [(0, 8, "P1"), (8, 12, "P2"), (12, 17, "P4"), (17, 26, "P3")])
        self.assertEqual(r.average("waiting"), 7.75)

    def test_rr_hand_calculation_and_boundary_arrival(self):
        r = simulate(self.control, "RR", quantum=2)
        self.assertEqual([m.start for m in r.metrics], [0, 2, 4, 8])
        self.assertEqual([m.completion for m in r.metrics], [22, 12, 26, 23])
        self.assertEqual(r.average("waiting"), 12.75)
        self.assertEqual(r.average("turnaround"), 19.25)
        r = simulate([Process("A", 0, 3, 1), Process("B", 2, 1, 1)], "RR", quantum=2)
        self.assertEqual(trace(r), [(0, 2, "A"), (2, 3, "B"), (3, 4, "A")])

    def test_srtf_hand_calculation(self):
        r = simulate(self.control, "SRTF")
        self.assertEqual(trace(r), [(0, 1, "P1"), (1, 5, "P2"), (5, 10, "P4"),
                                    (10, 17, "P1"), (17, 26, "P3")])
        self.assertEqual(r.average("waiting"), 6.5)

    def test_priority_preemption(self):
        r = simulate(self.control, "PRIORITY")
        self.assertEqual(trace(r), [(0, 2, "P1"), (2, 11, "P3"), (11, 17, "P1"),
                                    (17, 21, "P2"), (21, 26, "P4")])

    def test_equal_key_keeps_current_even_if_other_arrived_earlier(self):
        ps = [Process("A", 0, 4, 1), Process("B", 0, 2, 1), Process("C", 1, 1, 1)]
        self.assertEqual(trace(simulate(ps, "SRTF")), [(0, 2, "B"), (2, 3, "C"), (3, 7, "A")])
        self.assertEqual(trace(simulate(ps, "PRIORITY")), [(0, 4, "A"), (4, 6, "B"), (6, 7, "C")])

    def test_idle_and_single_task_switches(self):
        ps = [Process("A", 3, 3, 1), Process("B", 10, 1, 1)]
        r = simulate(ps, "RR", quantum=1)
        self.assertEqual(trace(r), [(0, 3, None), (3, 6, "A"), (6, 10, None), (10, 11, "B")])
        self.assertEqual(r.switches, 0)
        self.assertEqual(r.dispatches, 4)

    def test_mlfq_demotions(self):
        ps = [Process("A", 0, 9, 1), Process("B", 0, 9, 1)]
        r = simulate(ps, "MLFQ", quanta=(1, 2, 4), boost_interval=100)
        self.assertEqual(trace(r), [(0, 1, "A"), (1, 2, "B"), (2, 4, "A"), (4, 6, "B"),
                                    (6, 10, "A"), (10, 14, "B"), (14, 16, "A"), (16, 18, "B")])

    def test_mlfq_preemption_preserves_budget(self):
        ps = [Process("A", 0, 10, 1), Process("B", 4, 1, 1), Process("C", 0, 10, 1)]
        r = simulate(ps, "MLFQ", quanta=(1, 3, 6), boost_interval=100)
        self.assertEqual(trace(r)[:6], [(0, 1, "A"), (1, 2, "C"), (2, 4, "A"),
                                      (4, 5, "B"), (5, 6, "A"), (6, 9, "C")])

    def test_mlfq_boost_resets_level_and_budget(self):
        ps = [Process("A", 0, 8, 1), Process("B", 0, 8, 1)]
        r = simulate(ps, "MLFQ", quanta=(1, 2, 4), boost_interval=3)
        self.assertEqual(trace(r)[:4], [(0, 1, "A"), (1, 2, "B"), (2, 4, "A"), (4, 5, "B")])

    def test_aging_advances_p1_in_supplied_workload(self):
        ps = read_processes(Path(__file__).parent / "starve.txt")
        plain = simulate(ps, "PRIORITY").metrics[0]
        aged = simulate(ps, "PRIORITY", aging_interval=3).metrics[0]
        self.assertEqual((plain.start, plain.completion), (57, 63))
        self.assertLess(aged.start, plain.start)

    def test_input_validation(self):
        for ps in ([], [Process("A", -1, 2, 1)], [Process("A", 0, 0, 1)],
                   [Process("A", 0, 1, 1), Process("A", 1, 1, 1)]):
            with self.assertRaises(ValueError):
                simulate(ps, "FCFS")
        for kwargs in ({"quantum": 0}, {"aging_interval": 0}, {"quanta": (2, 2, 8)}, {"boost_interval": 0}):
            with self.assertRaises(ValueError):
                simulate(self.control, "PRIORITY", **kwargs)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "data.txt"
            path.write_text("\ufeff# test\nA 0 2 1 # comment\n\n", encoding="utf-8")
            self.assertEqual(read_processes(path), [Process("A", 0, 2, 1)])
            path.write_text("A 0 nope 1", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_processes(path)

    def test_randomized_conservation_and_metrics(self):
        rng = random.Random(20261029)
        variants = [(a, {}) for a in ("FCFS", "SJF", "RR", "SRTF", "PRIORITY", "MLFQ")]
        variants.append(("PRIORITY", {"aging_interval": 2}))
        for _ in range(60):
            ps = [Process(f"P{i}", rng.randrange(20), rng.randrange(1, 12), rng.randrange(1, 8))
                  for i in range(rng.randrange(1, 10))]
            for algorithm, kwargs in variants:
                r = simulate(ps, algorithm, **kwargs)
                executed = Counter()
                previous = 0
                by_pid = {p.pid: p for p in ps}
                for s in r.timeline:
                    self.assertEqual(s.start, previous)
                    self.assertGreater(s.end, s.start)
                    if s.pid is not None:
                        self.assertGreaterEqual(s.start, by_pid[s.pid].arrival)
                        executed[s.pid] += s.end - s.start
                    else:
                        self.assertFalse(any(p.arrival < s.end and executed[p.pid] < p.burst for p in ps))
                    previous = s.end
                self.assertEqual(executed, Counter({p.pid: p.burst for p in ps}))
                for m in r.metrics:
                    segments = [s for s in r.timeline if s.pid == m.pid]
                    self.assertEqual(m.start, segments[0].start)
                    self.assertEqual(m.completion, segments[-1].end)
                    self.assertEqual(m.waiting, m.completion - m.arrival - m.burst)
                    self.assertGreaterEqual(m.waiting, m.response)
                    self.assertGreaterEqual(m.response, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
