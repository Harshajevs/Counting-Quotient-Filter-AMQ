import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

class ReportValidationTests(unittest.TestCase):
    def check(self, rows, expected):
        spec=importlib.util.spec_from_file_location("validation",Path(__file__).parents[1]/"scripts/verify_report_experiments.py")
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"rows.csv"
            with p.open("w") as f:
                w=csv.DictWriter(f,fieldnames=["n_requested","n_inserted","found_positive"]);w.writeheader();w.writerows(rows)
            m.require_full_cqf_rows(p,expected,100)

    def test_partial_insert_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"incomplete"):
            self.check([dict(n_requested=100,n_inserted=99,found_positive=99)],1)

    def test_stale_appended_rows_are_rejected(self):
        row=dict(n_requested=100,n_inserted=100,found_positive=100)
        with self.assertRaisesRegex(ValueError,"rows"):
            self.check([row,row],1)

    def test_complete_expected_rows_pass(self):
        self.check([dict(n_requested=100,n_inserted=100,found_positive=100)],1)

if __name__=="__main__":unittest.main()
