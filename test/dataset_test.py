###############################################################################
# Global Imports
###############################################################################
import os
import shutil
import tempfile

###############################################################################
# Helper Imports
###############################################################################
from seraph.lib.common import CLASSFILE_NAME, SERAPH_FILENAME, PREFERRED_METADATA_FILENAME, DATA_DIR
from seraph.lib.history import HistoryManager
from _config import TEST_DATASET_BETA, SERAPH_FILE_CONTENTS

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.lib.dataset import SeraphDataset, derive_dataset, _serialize_seraph


###############################################################################
# Tests
###############################################################################
class TestDatasetMethods(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name
        SeraphDataset.create(self.dataset_path, SERAPH_FILE_CONTENTS, False)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_create_dataset(self):
        SeraphDataset.directory_is_seraph_dataset(self.dataset_path)

    def test_get_files(self):
        dataset = SeraphDataset(self.dataset_path)

        cls_filename = dataset.get_class_filename()
        self.assertEqual(cls_filename, CLASSFILE_NAME)

        data_dir = dataset.get_data_dir()
        expected = os.path.join(self.dataset_path, DATA_DIR)
        self.assertEqual(data_dir, expected)

        dataset_dir = dataset.get_dataset_root_dir()
        self.assertEqual(dataset_dir, self.dataset_path)

        history = dataset.get_history()
        self.assertIsInstance(history, HistoryManager)

        meta_filename = dataset.get_metadata_filename()
        self.assertEqual(meta_filename, PREFERRED_METADATA_FILENAME)

        seraph_filename = dataset.get_seraph_filename()
        self.assertEqual(seraph_filename, SERAPH_FILENAME)

        seraph_meta = dataset.get_seraph_metadata()
        meta_tmp = _serialize_seraph(seraph_meta)
        for key, value in SERAPH_FILE_CONTENTS.items():
            self.assertEqual(meta_tmp[key], value)

    def test_get_file_contents(self):
        dataset = SeraphDataset(TEST_DATASET_BETA)

        headers, records = dataset.get_metadata()
        self.assertEqual(headers, ["class_id", "class_name", "filename"])
        self.assertEqual(len(records), 10)

        classes = dataset.get_classes()
        self.assertEqual(classes, ["6.5 Creedmoor", "9x19"])

    def test_get_update_metadata(self):
        # Setup
        shutil.copytree(TEST_DATASET_BETA, self.dataset_path, dirs_exist_ok=True)
        dataset = SeraphDataset(self.dataset_path)

        headers, records = dataset.get_metadata()
        classes = dataset.get_classes()
        seraph = dataset.get_seraph_metadata()

        # Update
        headers += ["datum_id"]
        for idx, rec in enumerate(records):
            rec["datum_id"] = str(idx)
        records += [{
            "class_id": 0,
            "class_name": "6.5 Creedmoor",
            "filename": "65CD-0-X1fRvwEQOSNS-5.wav",
            "datum_id": len(records) + 1
        }]

        classes += ["5.56 NATO"]

        seraph.license = "BSD-2-Clause"

        dataset.set_multiple(
            metadata_headers=headers,
            metadata_records=records,
            classes=classes,
            seraph_metadata=seraph,
        ).save()

        # Verify
        dataset = SeraphDataset(self.dataset_path)

        headers_2, records_2 = dataset.get_metadata()
        classes_2 = dataset.get_classes()
        seraph_2 = dataset.get_seraph_metadata()

        self.assertEqual(headers_2, ["class_id", "class_name", "filename", "datum_id"])
        self.assertEqual(len(records_2), 11)
        self.assertEqual(classes_2, ["6.5 Creedmoor", "9x19", "5.56 NATO"])
        self.assertEqual(seraph_2.license, "BSD-2-Clause")

    def test_derive_dataset(self):
        os.unlink(os.path.join(self.dataset_path, SERAPH_FILENAME))
        os.unlink(os.path.join(self.dataset_path, CLASSFILE_NAME))
        os.unlink(os.path.join(self.dataset_path, PREFERRED_METADATA_FILENAME))
        shutil.rmtree(os.path.join(self.dataset_path, DATA_DIR))

        parent = SeraphDataset(TEST_DATASET_BETA)
        headers, records = parent.get_metadata()
        classes = parent.get_classes()
        seraph = parent.get_seraph_metadata()

        derive_dataset(parent, self.dataset_path, "tag:certusinnovations.com,2024:datasets:Derived")

        child = SeraphDataset(self.dataset_path)
        headers_2, records_2 = child.get_metadata()
        classes_2 = child.get_classes()
        seraph_2 = child.get_seraph_metadata()

        self.assertEqual(headers, headers_2)
        self.assertEqual(records, records_2)
        self.assertEqual(classes, classes_2)

        self.assertEqual(f"{seraph.uri}:{seraph.version}", seraph_2.viewOf)
        self.assertEqual(seraph_2.version, "v0.1.0")
        self.assertEqual(seraph_2.uri, "tag:certusinnovations.com,2024:datasets:Derived")

        self.assertEqual(len(os.listdir(child.get_data_dir())), 0)
