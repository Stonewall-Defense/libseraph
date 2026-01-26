###############################################################################
# Global Imports
###############################################################################
import os
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

from seraph.exec.prune import prune_files, prune_column, prune_rows, prune_records, prune_dupes


###############################################################################
# Tests
###############################################################################
class TestPruneMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name

        shutil.copytree(TEST_DATASET_ALPHA, self.dataset_path, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_prune_files(self):
        RECS_TO_PRUNE = 4

        orig_dataset = SeraphDataset(self.dataset_path)
        _, orig_recs = orig_dataset.get_metadata()
        orig_len = len(os.listdir(orig_dataset.get_data_dir()))

        orig_recs = orig_recs[:-RECS_TO_PRUNE]
        orig_dataset.set_metadata_records(orig_recs).save()

        self.runner.invoke(prune_files, [
            "--dataset_dir", self.dataset_path,
        ])

        new_dataset = SeraphDataset(self.dataset_path)
        new_len = len(os.listdir(new_dataset.get_data_dir()))
        self.assertEqual(new_len, orig_len - RECS_TO_PRUNE)

    def test_prune_records(self):
        RECS_TO_PRUNE = 4

        orig_dataset = SeraphDataset(self.dataset_path)
        rm_dir = orig_dataset.get_data_dir()
        _, orig_recs = orig_dataset.get_metadata()
        for rec in orig_recs[:RECS_TO_PRUNE]:
            os.unlink(os.path.join(rm_dir, rec["filename"]))

        self.runner.invoke(prune_records, [
            "--dataset_dir", self.dataset_path,
        ])

        new_dataset = SeraphDataset(self.dataset_path)
        _, new_recs = new_dataset.get_metadata()
        self.assertEqual(len(new_recs), len(orig_recs) - RECS_TO_PRUNE)

    def test_prune_rows(self):
        self.runner.invoke(prune_rows, [
            "--dataset_dir", self.dataset_path,
            "--column_name", "platform",
            "--rm_row_val", "20 Gauge"
        ])

        dataset = SeraphDataset(self.dataset_path)
        _, records = dataset.get_metadata()
        self.assertEqual(len(records), 25)

    def test_prune_cols(self):
        self.runner.invoke(prune_column, [
            "--dataset_dir", self.dataset_path,
            "--column_name", "platform",
        ])

        dataset = SeraphDataset(self.dataset_path)
        headers, _ = dataset.get_metadata()

        self.assertNotIn("platform", headers)

    def test_prune_dupes(self):
        orig_dataset = SeraphDataset(self.dataset_path)
        _, orig_recs = orig_dataset.get_metadata()
        orig_len = len(orig_recs)
        orig_recs.append({
            "class_id": "4",
            "class_name": "223 Remington",
            "platform": "Savage 223",
            "filename": "SAV_223-0-IaO6gvZyLJyE-4.wav"
        })

        orig_dataset.set_metadata_records(orig_recs).save()

        self.runner.invoke(prune_dupes, [
            "--dataset_dir", self.dataset_path,
            "--identity_column", "filename",
        ])

        new_dataset = SeraphDataset(self.dataset_path)
        _, new_recs = new_dataset.get_metadata()
        self.assertEqual(len(new_recs), orig_len)
