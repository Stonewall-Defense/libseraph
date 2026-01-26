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
import torch
import torchaudio

###############################################################################
# Helper Imports
###############################################################################
from seraph.lib.common import read_json
from seraph.lib.dataset import SeraphDataset
from _config import TEST_DATASET_ALPHA, TEST_DATASET_BETA

###############################################################################
# Test Imports
###############################################################################
import unittest

from seraph.exec.audio import audio_add_duration, audio_clip_files, audio_import, audio_prune, audio_resample, audio_verify


###############################################################################
# Tests
###############################################################################
class TestAudioMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = CliRunner()

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.dataset_path = self.tmp_dir.name

        shutil.copytree(TEST_DATASET_ALPHA, self.dataset_path, dirs_exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_audio_duration(self):
        self.runner.invoke(audio_add_duration, [
            "--dataset_dir", self.dataset_path,
        ])

        dataset = SeraphDataset(self.dataset_path)
        headers, records = dataset.get_metadata()

        self.assertIn("duration_secs", headers)
        for record in records:
            self.assertLessEqual(float(record["duration_secs"]), 1.0)

    def test_audio_clip(self):
        self.runner.invoke(audio_add_duration, [
            "--dataset_dir", self.dataset_path,
        ])
        self.runner.invoke(audio_clip_files, [
            "--dataset_dir", self.dataset_path,
            "--clip_duration_secs", "0.5"
        ])

        dataset = SeraphDataset(self.dataset_path)
        headers, records = dataset.get_metadata()

        self.assertIn("clip_id", headers)
        for record in records:
            self.assertLessEqual(float(record["duration_secs"]), 0.5)
            self.assertLessEqual(int(record["clip_id"]), 2)

    def test_audio_import(self):
        self.runner.invoke(audio_import, [
            "--dataset_dir", self.dataset_path,
            "--import_dir", TEST_DATASET_BETA,
        ])

        dataset = SeraphDataset(self.dataset_path)
        _, records = dataset.get_metadata()

        self.assertEqual(len(records), 40)

    def test_audio_resample_ok(self):
        self.runner.invoke(audio_resample, [
            "--dataset_dir", self.dataset_path,
            "--target_sr", "44100",
        ])

        dataset = SeraphDataset(self.dataset_path)
        seraph = dataset.get_seraph_metadata()

        if seraph.mediaMetadata is None:
            raise ValueError("No media metadata")
        self.assertEqual(seraph.mediaMetadata["audio"]["wav"]["sampleRate"], 44100)

    def test_audio_resample_fail(self):
        result = self.runner.invoke(audio_resample, [
            "--dataset_dir", self.dataset_path,
            "--target_sr", "96000",
        ])

        self.assertTrue(str(result.exception).startswith("Cannot safely upsample file"))

    def test_audio_verify_ok(self):
        result = self.runner.invoke(audio_verify, [
            "--dataset_dir", self.dataset_path,
        ])

        expected = "No dataset contract violations!\n\n"

        print(result.output)

        self.assertTrue(result.output.endswith(expected))

    def test_audio_verify_fail(self):
        dataset = SeraphDataset(self.dataset_path)
        seraph = dataset.get_seraph_metadata()
        if seraph.mediaMetadata is None:
            raise ValueError("No media metadata")
        seraph.mediaMetadata["audio"]["wav"]["sampleRate"] = 96000
        dataset.set_seraph_metadata(seraph).save()

        self.runner.invoke(audio_verify, [
            "--dataset_dir", self.dataset_path,
            "--output_format", "json",
        ])

        dataset = SeraphDataset(self.dataset_path)
        _, records = dataset.get_metadata()

        errors = read_json(os.path.join(self.dataset_path, "verification-errors.json"))
        self.assertEqual(len(records), len(errors))
        for err in errors:
            self.assertEqual(err["sample_rate"], 48000)

    def test_audio_prune(self):
        dataset = SeraphDataset(self.dataset_path)
        _, records = dataset.get_metadata()
        fq_data_dir = dataset.get_data_dir()

        target_file = records[0]
        fq_target = os.path.join(fq_data_dir, target_file["filename"])
        wave, sr = torchaudio.load(fq_target, normalize=True)
        wave = torch.zeros_like(wave)
        torchaudio.save(fq_target, wave, sample_rate=sr, encoding="PCM_S", bits_per_sample=16)

        self.runner.invoke(audio_prune, [
            "--dataset_dir", self.dataset_path,
            "--remove_silence",
        ])

        dataset = SeraphDataset(self.dataset_path)
        _, records_2 = dataset.get_metadata()

        self.assertEqual(len(records), len(records_2) + 1)
