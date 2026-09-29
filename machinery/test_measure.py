import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import measure
from fixtures import matches


class Accounting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        source = Path(__file__).with_name("probe.c")
        cls.binary = cls.root / "probe"
        subprocess.run(
            ["cc", "-O2", "-pthread", str(source), "-o", str(cls.binary)], check=True
        )
        cls.cpu = [min(os.sched_getaffinity(0))]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_probe(self, name, timeout=2):
        return measure.run(
            [str(self.binary), name],
            self.root / self._testMethodName,
            dict(os.environ),
            self.cpu,
            timeout,
        )

    def test_sleep_counts_wall_not_cpu(self):
        r = self.run_probe("sleep")
        self.assertEqual(r["status"], "ok")
        self.assertGreater(r["process_wall_ns"], 140_000_000)
        self.assertLess(r["process_cpu_ns"], 50_000_000)

    def test_process_cpu_unit(self):
        r = self.run_probe("cpu")
        self.assertGreater(r["process_cpu_ns"], 140_000_000)
        self.assertGreaterEqual(r["process_wall_ns"] + 5_000_000, r["process_cpu_ns"])

    def test_worker_thread_cpu_is_included(self):
        r = self.run_probe("threads")
        self.assertGreater(r["process_cpu_ns"], 140_000_000)

    def test_launcher_memory_does_not_contaminate_child_peak(self):
        retained = bytearray(96 * 1024 * 1024)
        r = self.run_probe("memory")
        self.assertEqual(len(retained), 96 * 1024 * 1024)
        self.assertLess(r["peak_rss_bytes"], 50 * 1024 * 1024)

    def test_waited_descendant_cpu_included(self):
        r = self.run_probe("tree")
        self.assertGreater(r["process_cpu_ns"], 140_000_000)

    def test_touched_memory_high_water(self):
        r = self.run_probe("memory")
        self.assertGreater(r["peak_rss_bytes"], 30 * 1024 * 1024)
        self.assertLess(r["peak_rss_bytes"], 50 * 1024 * 1024)

    def test_failure_is_not_a_measurement_success(self):
        r = self.run_probe("fail")
        self.assertEqual(r["status"], "exit_error")
        self.assertEqual(r["exit_code"], 7)

    def test_timeout_stops_process(self):
        r = self.run_probe("timeout", 0.05)
        self.assertEqual(r["status"], "timeout")

    def test_boolean_is_not_an_integer_result(self):
        self.assertFalse(matches(True, 1))
        self.assertFalse(matches([True], [1]))
        self.assertTrue(matches([2], [2]))


class Protocol(unittest.TestCase):
    def test_invalid_and_incomplete_protocols_are_rejected(self):
        from run import valid_protocol

        observed = {
            "event_order": ["ready", "result"],
            "malformed_lines": 0,
            "process_wall_ns": 100,
            "process_cpu_ns": 100,
        }
        value = {
            "jobs": 1,
            "execution_wall_ns": 50,
            "execution_cpu_ns": 40,
            "result": "42",
        }
        self.assertTrue(valid_protocol(observed, value, "go", 1))
        self.assertFalse(valid_protocol(observed, value, "baml", 1))
        self.assertFalse(
            valid_protocol(observed, value | {"execution_cpu_ns": -1}, "go", 1)
        )
        self.assertFalse(
            valid_protocol(observed, value | {"execution_cpu_ns": True}, "go", 1)
        )
        self.assertFalse(
            valid_protocol(observed, value | {"execution_wall_ns": 2000000}, "go", 1)
        )
        self.assertFalse(
            valid_protocol(
                observed | {"event_order": ["ready", "result", "result"]},
                value,
                "go",
                1,
            )
        )
        self.assertFalse(
            valid_protocol(observed | {"malformed_lines": 1}, value, "go", 1)
        )


if __name__ == "__main__":
    unittest.main()
