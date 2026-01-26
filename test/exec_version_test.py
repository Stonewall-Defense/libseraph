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
from seraph.lib.common import today
from seraph.lib.dataset import SeraphDataset
from seraph.lib.history import ChangeRecord, ChangeType, VersionBumpType
from _config import TEST_DATASET_ALPHA

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.exec.version import version_show, version_list, version_bump


###############################################################################
# Tests
###############################################################################
class TestVersionMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name

        shutil.copytree(TEST_DATASET_ALPHA, self.dataset_path, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_version_show(self):
        orig_dataset = SeraphDataset(self.dataset_path)
        orig_classes = orig_dataset.get_classes()
        orig_classes = orig_classes[:-1]

        change_record = ChangeRecord(
            bump_type=VersionBumpType.MAJOR,
            change_type=ChangeType.REMOVE,
            message="Removed a class",
            is_import=False,
        )

        orig_dataset.set_classes(orig_classes, change_record=change_record).save()

        result = self.runner.invoke(version_show, [
            "--dataset_dir", self.dataset_path,
        ])

        t = "        "
        expected = f"v0.0.0 --> v0.1.0 - {today()}\n\nRemoved\n{t}- Pruned 1960 files without corresponding metadata entries\n{t}- BREAKING - Removed a class\n"

        self.assertEqual(result.output, expected)

    def test_version_bump(self):
        orig_dataset = SeraphDataset(self.dataset_path)
        orig_classes = orig_dataset.get_classes()
        orig_classes = orig_classes[:-1]

        change_record = ChangeRecord(
            bump_type=VersionBumpType.MAJOR,
            change_type=ChangeType.REMOVE,
            message="Removed a class",
            is_import=False,
        )

        orig_dataset.set_classes(orig_classes, change_record=change_record).save()

        self.runner.invoke(version_bump, [
            "--dataset_dir", self.dataset_path,
        ])

        new_dataset = SeraphDataset(self.dataset_path)
        seraph = new_dataset.get_seraph_metadata()
        self.assertEqual(seraph.version, "0.1.0")

    def test_version_bump_release(self):
        orig_dataset = SeraphDataset(self.dataset_path)
        orig_classes = orig_dataset.get_classes()
        orig_classes = orig_classes[:-1]

        change_record = ChangeRecord(
            bump_type=VersionBumpType.MAJOR,
            change_type=ChangeType.REMOVE,
            message="Removed a class",
            is_import=False,
        )

        orig_dataset.set_classes(orig_classes, change_record=change_record).save()

        self.runner.invoke(version_bump, [
            "--dataset_dir", self.dataset_path,
            "--initial_release"
        ])

        new_dataset = SeraphDataset(self.dataset_path)
        seraph = new_dataset.get_seraph_metadata()
        self.assertEqual(seraph.version, "1.0.0")
