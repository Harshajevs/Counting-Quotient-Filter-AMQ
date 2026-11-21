import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np

SPEC = importlib.util.spec_from_file_location("audit_workloads", Path(__file__).parents[1] / "scripts/audit_workloads.py")

class AuditTests(unittest.TestCase):
    def run_audit(self, positives, negatives, declared):
        module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            np.asarray(positives,dtype="<u8").tofile(root/"pos.bin")
            np.asarray(negatives,dtype="<u8").tofile(root/"neg.bin")
            return module.audit_pair(root/"pos.bin",root/"neg.bin",declared)

    def test_duplicate_uniform_is_detected(self):
        with self.assertRaisesRegex(ValueError,"distinct"):
            self.run_audit([1,1,2],[3,4],3)

    def test_true_member_in_negative_stream_is_detected(self):
        with self.assertRaisesRegex(ValueError,"negative"):
            self.run_audit([1,2,3],[4,2],3)

    def test_repeated_zipf_keys_are_allowed_with_correct_distinct_count(self):
        r=self.run_audit([1,1,2,1],[3,4],2)
        self.assertEqual(r["distinct_keys"],2)
        self.assertEqual(r["max_frequency"],3)
        self.assertEqual(r["negative_count"],2)

if __name__=="__main__": unittest.main()
