"""Check measurement boundaries and failure rejection, not benchmark algorithms."""
from pathlib import Path
import sys
import tempfile
import unittest

from runner import Child
from fixtures import matches

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
        c.batch(1,c.p.pid)
        batch = c.batch(4,c.p.pid)
        usage = c.finish()
        self.assertGreaterEqual(batch['wall_s'],0.07)
        self.assertLess(batch['cpu_s_ticks'],batch['wall_s'])
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
        c.batch(1,c.p.pid)
        with self.assertRaisesRegex(RuntimeError,'exit 7'): c.finish()


if __name__ == '__main__': unittest.main()
