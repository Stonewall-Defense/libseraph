###############################################################################
# Global Imports
###############################################################################
import shutil
import tempfile

###############################################################################
# 3PP Imports
###############################################################################
from click.testing import CliRunner

###############################################################################
# Helper Imports
###############################################################################
from seraph.lib.dataset import SeraphDataset
from _config import TEST_DATASET_ALPHA

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.exec.splits import train_test_splits, fold_splits


###############################################################################
# Tests
###############################################################################
class TestSplitsMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name

        shutil.copytree(TEST_DATASET_ALPHA, self.dataset_path, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_ttv_60_20_20(self):
        self.runner.invoke(train_test_splits, [
            "--dataset_dir", self.dataset_path,
            "--split_type", "60_20_20",
        ])
        dataset = SeraphDataset(self.dataset_path)
        headers, records = dataset.get_metadata()

        self.assertIn("split", headers)

        sums = {
            "train": 0,
            "test": 0,
            "val": 0,
        }

        for record in records:
            sums[record["split"]] += 1

        self.assertEqual(sums["train"], 18)
        self.assertEqual(sums["test"], 6)
        self.assertEqual(sums["val"], 6)

    def test_ttv_80_20(self):
        self.runner.invoke(train_test_splits, [
            "--dataset_dir", self.dataset_path,
            "--split_type", "80_20",
        ])
        dataset = SeraphDataset(self.dataset_path)
        headers, records = dataset.get_metadata()

        self.assertIn("split", headers)

        sums = {
            "train": 0,
            "test": 0,
            "val": 0,
        }

        for record in records:
            sums[record["split"]] += 1

        self.assertEqual(sums["train"], 24)
        self.assertEqual(sums["test"], 6)
        self.assertEqual(sums["val"], 0)

    def test_xfold_5(self):
        self.runner.invoke(fold_splits, [
            "--dataset_dir", self.dataset_path,
            "--n_folds", "5",
        ])
        dataset = SeraphDataset(self.dataset_path)
        headers, records = dataset.get_metadata()

        self.assertIn("fold", headers)

        sums = [0, 0, 0, 0, 0]

        for record in records:
            fold = int(record["fold"])
            sums[fold] += 1

        for s in sums:
            self.assertEqual(s, 6)
