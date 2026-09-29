"""Check measurement boundaries and failure rejection, not benchmark algorithms."""
from pathlib import Path
import sys
import tempfile
import unittest

from runner import Child
from fixtures import matches
from service import window_metrics

PROGRAM = '''
import os, sys, time
configuration = sys.stdin.readline()
print('@ready',flush=True)
while count := int(sys.stdin.readline()):
    for _ in range(count):
        time.sleep(0.02)
        print('@result '+str(os.getpid()),flush=True)
    print('@done',flush=True)
'''


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.child = None

    def tearDown(self):
        if self.child: self.child.abort()
        self.temp.cleanup()

    def launch(self, program=PROGRAM):
        self.child = Child({'command':[sys.executable,'-c',program]}, '{}', 'off',
                           Path(self.temp.name)/'run')
        self.child.ready()
        return self.child

    def test_warmup_and_measurement_share_process_and_wait_is_not_cpu(self):
        c = self.launch()
        c.batch(1,c.measure_pid)
        batch = c.batch(4,c.measure_pid)
        usage = c.finish()
        self.assertGreaterEqual(batch['wall_s'],0.07)
        self.assertLess(batch['cpu_s'],batch['wall_s'])
        self.assertGreater(usage['peak_rss_bytes'],0)
        self.assertIsNotNone(usage['first_correct_result_s'])

    def test_incorrect_result_is_rejected(self):
        c = self.launch()
        with self.assertRaises(AssertionError): c.batch(1,-1)

    def test_oracle_distinguishes_json_boolean_from_number(self):
        self.assertFalse(matches([{'total_cents':True}], [{'total_cents':1}]))
        self.assertTrue(matches({'b':2, 'a':1}, {'a':1, 'b':2}))

    def test_nonzero_exit_is_rejected_after_correct_result(self):
        c = self.launch(PROGRAM+'\nsys.exit(7)\n')
        c.batch(1,c.measure_pid)
        with self.assertRaisesRegex(RuntimeError,'exit 7'): c.finish()

    def test_peak_rss_excludes_large_launcher(self):
        ballast = bytearray(128 * 1024 * 1024)
        c = self.launch()
        c.batch(1,c.measure_pid)
        usage = c.finish()
        self.assertLess(usage['peak_rss_bytes'],len(ballast)//2)

    def test_http_drain_does_not_extend_offered_load_window(self):
        entries = [{'scheduled_s':i/100,'latency_s':.001,'correct':True} for i in range(1000)]
        entries[-1] = {'scheduled_s':9.99,'latency_s':10,'correct':False}
        m = window_metrics(entries,100,20,100)
        self.assertEqual(m['measurement_window_s'],10)
        self.assertEqual(m['correct_rps'],99.9)
        self.assertEqual(m['drain_s'],10)
        self.assertIsNotNone(m['p99_ms'])

    def test_http_late_results_and_failures_remain_visible(self):
        entries = [{'scheduled_s':i/100,'latency_s':.001,'correct':True} for i in range(1000)]
        for i in range(20): entries[i] = {'scheduled_s':i/100,'latency_s':10,'correct':False}
        m = window_metrics(entries,100,20,100)
        self.assertEqual(m['p99_ms'],10000)
        self.assertEqual(m['goodput_rps'],98)


if __name__ == '__main__': unittest.main()
