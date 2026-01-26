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
from _config import TEST_DATASET_ALPHA

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.exec.classes import switch_classes, merge_classes, rename_classes, merge_classes_regex, drop_class, _class_balance_impl, classes_compose


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

    # @patch("builtins.input", return_value="*+g$")
    # def test_classes_merge_regex(self):
    #     result = self.runner.invoke(merge_classes_regex, [
    #         "--dataset_dir", self.dataset_path,
    #         "--target_class_name", "shotgun",
    #     ])
    #     print(result.exception)
    #     dataset = SeraphDataset(self.dataset_path)
    #     classes = dataset.get_classes()
    #     self.assertEqual(classes, [".380 ACP", "223 Remington", "5.56x45", "shotgun"])

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

    def test_classes_drop(self):
        self.runner.invoke(drop_class, [
            "--dataset_dir", self.dataset_path,
            "--class_name", "5.56x45",
        ])
        dataset = SeraphDataset(self.dataset_path)
        classes = dataset.get_classes()
        self.assertEqual(classes, [".380 ACP", "12g", "16g", "20g", "223 Remington"])

    def test_classes_compose(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            shutil.copy("test/res/compose.csv", tmp_dir)
            os.rename(os.path.join(tmp_dir, "compose.csv"), os.path.join(tmp_dir, "metadata.csv"))

            self.runner.invoke(classes_compose, [
                "--target_dir", tmp_dir,
                "--compose_col", "dept",
            ])
            classes = read_json(os.path.join(tmp_dir, "classes.json"))
            self.assertEqual(classes, ["billing", "shipping"])

    def test_classes_balance(self):
        dataset = SeraphDataset(self.dataset_path)
        _, metadata = dataset.get_metadata()
        classes = dataset.get_classes()

        balance = _class_balance_impl(metadata, classes)
        result = balance[0][1]

        for cls in classes:
            self.assertEqual(result[cls], 5.0)
