###############################################################################
# Global Imports
###############################################################################
import tempfile

###############################################################################
# Helper Imports
###############################################################################
from seraph.lib.dataset import SeraphDataset
from _config import TEST_DATASET_BETA, SERAPH_FILE_CONTENTS

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.lib.history import VersionBumpType, ChangeType, ChangeRecord, ImportRecord, VersionRecord


###############################################################################
# Config
###############################################################################
OLD_VERSION = "0.0.0"
NEW_VERSION = "0.1.0"


###############################################################################
# Tests
###############################################################################
class TestHistoryMethods(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name
        SeraphDataset.create(self.dataset_path, SERAPH_FILE_CONTENTS, False)

        beta = SeraphDataset(TEST_DATASET_BETA)
        beta_seraph = beta.get_seraph_metadata()
        beta_classes = beta.get_classes()

        self.change_1 = ChangeRecord(
            bump_type=VersionBumpType.MAJOR,
            change_type=ChangeType.ADD,
            message=f"Added data from {beta_seraph.uri} to dataset",
            is_import=True,
        )

        self.change_2 = ChangeRecord(
            bump_type=VersionBumpType.MINOR,
            change_type=ChangeType.CHANGE,
            message="Added metadata column for datum_id: `datum_id`",
            is_import=False,
        )

        self.import_rec = ImportRecord(
            uri=beta_seraph.uri,
            version=beta_seraph.version,
            name=beta_seraph.name,
            classes=beta_classes,
        )

        self.dataset = SeraphDataset(self.dataset_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_save_updates_load_sources(self):
        hist = self.dataset.get_history()

        hist.register_all(changes=[self.change_1], import_recs=[self.import_rec]).save(OLD_VERSION)

        imports, changes = hist.load_changes()

        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0], self.import_rec)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0], self.change_1)

        sources = hist.load_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0], self.import_rec)

    def test_bump_version_with_prov(self):
        hist = self.dataset.get_history()
        hist.register(change=self.change_2, import_rec=self.import_rec).save(OLD_VERSION)
        hist.update_version(NEW_VERSION)

        imports, changes = hist.load_changes()
        self.assertEqual(len(imports), 0)
        self.assertEqual(len(changes), 0)

        prov = hist.check_prov_submission(NEW_VERSION)
        self.assertFalse(prov)
        hist.mark_prov_submission(NEW_VERSION)
        prov = hist.check_prov_submission(NEW_VERSION)
        self.assertTrue(prov)

    def test_load_change_list(self):
        hist = self.dataset.get_history()
        hist.register(change=self.change_2, import_rec=self.import_rec).save(OLD_VERSION)
        hist.update_version(NEW_VERSION)

        versions = hist.load_change_list()
        self.assertEqual(len(versions), 1)

        expected_version = VersionRecord(
            version=NEW_VERSION,
            datetime=versions[0].datetime,
            prov_was_submitted=False,
            imports=[],
            changes=[],
        )

        self.assertEqual(versions[0], expected_version)
