import importlib.util
import math
from pathlib import Path
import unittest
import pandas as pd

class AssetSemanticsTests(unittest.TestCase):
    def test_legacy_zero_does_not_create_a_bloom_delete_measurement(self):
        spec=importlib.util.spec_from_file_location('assets',Path(__file__).parents[1]/'scripts/make_research_assets.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        group=pd.DataFrame([dict(filter='bloom',n_inserted=100,n_requested=100,delete_ops_sec=0)])
        mean,_=module.stat(group,'delete_ops_sec')
        self.assertTrue(math.isnan(mean),'unsupported deletion must remain unavailable, not zero throughput')

if __name__=='__main__':unittest.main()
