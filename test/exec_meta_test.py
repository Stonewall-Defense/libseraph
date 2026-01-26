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
from seraph.lib.common import read_json
from seraph.lib.dataset import SeraphDataset
from seraph.lib.history import ChangeRecord, ChangeType, VersionBumpType
from _config import TEST_DATASET_ALPHA

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.exec.meta import meta_init, meta_verify, meta_derive, meta_datum_id


###############################################################################
# Tests
###############################################################################
class TestMetaMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name

        shutil.copytree(TEST_DATASET_ALPHA, self.dataset_path, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_meta_verify_fail(self):
        dataset = SeraphDataset(self.dataset_path)
        headers, _ = dataset.get_metadata()
        dataset.set_metadata_headers(headers + ["filename"]).save()

        self.runner.invoke(meta_verify, [
            "--dataset_dir", self.dataset_path,
            "--output_format", "json"
        ])

        errors = read_json(os.path.join(self.dataset_path, "metadata-verification-errors.json"))
        self.assertEqual(errors["dupe_headers"], ["filename"])

    def test_meta_verify_ok(self):
        result = self.runner.invoke(meta_verify, [
            "--dataset_dir", self.dataset_path,
        ])
        expected = "No metadata column issues\n"
        self.assertEqual(result.output, expected)

    def test_meta_derive(self):
        with tempfile.TemporaryDirectory() as derived_dir:
            self.runner.invoke(meta_derive, [
                "--dataset_dir", derived_dir,
                "--parent_dataset", self.dataset_path,
                "--uri", "tag:certusinnovations.com,2024:dataset:derived",
            ])

            dataset = SeraphDataset(derived_dir)
            seraph = dataset.get_seraph_metadata()
            self.assertEqual(seraph.uri, "tag:certusinnovations.com,2024:dataset:derived")
            self.assertEqual(seraph.version, "v0.1.0")
            self.assertEqual(seraph.viewOf, "tag:certusinnovations.com,2024:datasets:ComponentAlpha:v0.0.0")

    def test_meta_datum_id(self):
        self.runner.invoke(meta_datum_id, [
            "--dataset_dir", self.dataset_path,
        ])
        dataset = SeraphDataset(self.dataset_path)
        headers, records = dataset.get_metadata()

        self.assertIn("datum_id", headers)
        self.assertEqual(records[0]["datum_id"], "0")
