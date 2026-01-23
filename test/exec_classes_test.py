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

from seraph.exec.classes import switch_classes, merge_classes, rename_classes, merge_classes_regex, drop_class, classes_check_balance, classes_compose


###############################################################################
# Tests
###############################################################################
class TestClassesMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name

        shutil.copytree(TEST_DATASET_ALPHA, self.dataset_path, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_classes_switch(self):
        self.runner.invoke(switch_classes, [
            "--dataset_dir", self.dataset_path,
            "--new_class_col", "platform",
            "--new_name_for_current_class_col", "caliber",
        ])
        dataset = SeraphDataset(self.dataset_path)
        classes = dataset.get_classes()
        self.assertEqual(classes, ["12 Gauge", "16 Gauge", "20 Gauge", "ACP", "AR-15", "Savage 223"])

    def test_classes_merge(self):
        self.runner.invoke(merge_classes, [
            "--dataset_dir", self.dataset_path,
            "--target_class_name", "shotgun",
            "--classes_to_merge", "12g",
            "--classes_to_merge", "16g",
            "--classes_to_merge", "20g",
        ])
        dataset = SeraphDataset(self.dataset_path)
        classes = dataset.get_classes()
        self.assertEqual(classes, [".380 ACP", "223 Remington", "5.56x45", "shotgun"])

    def test_classes_rename_fail(self):
        result = self.runner.invoke(rename_classes, [
            "--dataset_dir", self.dataset_path,
            "--new_class_name", "223 Remington",
            "--old_class_name", "5.56x45",
        ])
        self.assertEqual(result.exit_code, 1)

        result = self.runner.invoke(rename_classes, [
            "--dataset_dir", self.dataset_path,
            "--new_class_name", ".223/5.56",
            "--old_class_name", "5.56 NATO",
        ])
        self.assertEqual(result.exit_code, 1)

    def test_classes_rename_ok(self):
        self.runner.invoke(rename_classes, [
            "--dataset_dir", self.dataset_path,
            "--new_class_name", "5.56 NATO",
            "--old_class_name", "5.56x45",
        ])
        dataset = SeraphDataset(self.dataset_path)
        classes = dataset.get_classes()
        self.assertEqual(classes, [".380 ACP", "12g", "16g", "20g", "223 Remington", "5.56 NATO"])
