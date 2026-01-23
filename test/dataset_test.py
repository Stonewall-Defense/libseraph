###############################################################################
# Global Imports
###############################################################################
import os
import shutil
import tempfile

###############################################################################
# Helper Imports
###############################################################################
from seraph.lib.history import HistoryManager
from _config import TEST_DATASET_BETA

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.lib.dataset import SeraphDataset, derive_dataset, _serialize_seraph
from seraph.lib.dataset import CLASSFILE_NAME, SERAPH_FILENAME, PREFERRED_METADATA_FILENAME, DATA_DIR


###############################################################################
# Helpers
###############################################################################
_EXAMPLE_FILE_CONTENTS = {
    "uri": "tag:certusinnovations.com,2024:datasets:ExampleFileContents",
    "version": "v0.0.0",
    "name": "Example File Contents",
    "authors": [
        {
            "uri": "tag:certusinnovations.com,2024:agents:RyanQuinn",
            "name": "Ryan Quinn",
            "roles": [
                "associatedWith"
            ],
            "givenName": None,
            "familyName": None,
            "identifierScheme": "tag",
            "email": None,
            "affiliations": None
        }
    ],
    "keywords": [],
    "creationDate": "2026-01-23T13:27:00Z",
    "mediaType": "audio",
    "mediaSubtype": "wav",
    "license": "https://opensource.org/licenses/MIT",
}


###############################################################################
# Tests
###############################################################################
class TestDatasetMethods(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name
        SeraphDataset.create(self.dataset_path, _EXAMPLE_FILE_CONTENTS, False)

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
        for key, value in _EXAMPLE_FILE_CONTENTS.items():
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
