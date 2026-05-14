###############################################################################
# Global Imports
###############################################################################
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict, dataclass
from enum import Enum
import os
import shutil
import sys
from typing import Any, Optional
import warnings


###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print
from rich.table import Table
from tqdm import tqdm
from tinytag import TinyTag
import torch
import torchaudio


###############################################################################
# Local Imports
###############################################################################
from ..lib import REQUIRED_METADATA_FIELD_NAMES, REQUIRED_METADATA_IMPORT_COLS, VERIFY_OUTPUT_FORMATS
from ..lib import str_to_enum, write_csv, write_json
from ..lib import SeraphDataset, VersionBumpType, ChangeType, ChangeRecord, ImportRecord, SeraphMetadataError, VerifyOutputFormat, SupportedMediaType


###############################################################################
# Config
###############################################################################
warnings.filterwarnings("ignore", category=UserWarning)


###############################################################################
# Enums
###############################################################################
class AudioBaseMergeStrategy(Enum):
    REJECT = "reject"
    PUSH_DOWN = "push_down"


class AudioMixMergeStrategy(Enum):
    REJECT = "reject"
    MIX_DOWN = "mix_down"
    PUSH_DOWN = "push_down"


class MetadataFieldMergeStrategy(Enum):
    APPEND = "append"
    TRUNCATE = "truncate"


class MetadataColumnConflictStrategy(Enum):
    REJECT = "reject"
    REPLACE = "replace"
    KEEP = "keep"


class ClipEndStrategy(Enum):
    EXTEND = "extend"
    PARTIAL = "partial"
    DISCARD = "discard"


AUDIO_BASE_MERGE_STRATEGIES = [val.value for val in AudioBaseMergeStrategy]
AUDIO_MIX_MERGE_STRATEGIES = [val.value for val in AudioMixMergeStrategy]

METADATA_FIELD_MERGE_STRATEGIES = [val.value for val in MetadataFieldMergeStrategy]
METADATA_COLUMN_CONFLICT_STRATEGIES = [val.value for val in MetadataColumnConflictStrategy]

CLIP_END_STRAEGIES = [val.value for val in ClipEndStrategy]


###############################################################################
# Classes
###############################################################################
@dataclass
class Clip:
    clip_filename: str
    start_secs: float
    end_secs: float


@dataclass
class FileToClip:
    filename: str
    clips: list[Clip]


@dataclass
class VerifyError:
    filename: str
    subtype: Optional[str]
    sample_rate: Optional[int]
    channels: Optional[int]
    bit_depth: Optional[int]
    is_empty: bool
    no_audio: bool

    def has_violation(self):
        return self.subtype or self.sample_rate or self.channels or self.bit_depth or self.is_empty or self.no_audio


###############################################################################
# Constants
###############################################################################
METADATA_FIELDS_TO_STRIP = ["sample_rate", "num_channels"]
DURATION_COL_DEFAULT_NAME = "duration_secs"


###############################################################################
# Helpers
###############################################################################
def _prune_remote_data(remote_dataset: SeraphDataset,
                       class_select: Optional[list[str]],
                       class_exclude: Optional[list[str]],
                       split_select: Optional[str],
                       fold_select: Optional[str],
                       min_length_secs: Optional[int],
                       duration_col_name: Optional[str],
                       ):
    # Nothing to be done, so bail out
    if not class_select and not class_exclude and not min_length_secs:
        return

    # Class Selection
    if class_select:
        cls_select_fn = lambda rec: ((rec["class_name"] if isinstance(rec, dict) else rec) in class_select)         # noqa
    elif class_exclude:
        cls_select_fn = lambda rec: ((rec["class_name"] if isinstance(rec, dict) else rec) not in class_exclude)    # noqa
    else:
        cls_select_fn = lambda _: True                                      # noqa

    classes = remote_dataset.get_classes()
    _, metadata_records = remote_dataset.get_metadata()

    new_classes = [c for c in classes if cls_select_fn(c)]

    # Set up other selection criteria for metadata only
    if min_length_secs and duration_col_name:
        dur_select_fn = lambda rec: (float(rec[duration_col_name]) >= min_length_secs) # noqa
    else:
        dur_select_fn = lambda _: True                                          # noqa

    # Split or fold selection criteria
    if split_select:
        fs_select_fn = lambda rec: ((rec.get("split", None) if isinstance(rec, dict) else rec) == split_select) # noqa
    elif fold_select:
        fs_select_fn = lambda rec: ((rec.get("fold", None) if isinstance(rec, dict) else rec) == fold_select) # noqa
    else:
        fs_select_fn = lambda _: True # noqa

    select_fns = [cls_select_fn, dur_select_fn, fs_select_fn]

    # Down-select
    new_metadata = [m for m in metadata_records if all([s(m) for s in select_fns])]

    remote_dataset.set_classes(new_classes).set_metadata_records(new_metadata)
    return new_classes


def _merge_classes(local_dataset: SeraphDataset, remote_dataset: SeraphDataset) -> tuple[list[str], dict[int, int]]:
    local_classes = local_dataset.get_classes()
    if not isinstance(local_classes, list):
        raise NotImplementedError("For now, only lists of classes are supported: check local dataset")

    remote_classes = remote_dataset.get_classes()
    if not isinstance(remote_classes, list):
        raise NotImplementedError("For now, only lists of classes are supported: check remote dataset")

    remote_class_num_mapping = {}
    for idx, rem_cls in enumerate(remote_classes):
        if rem_cls not in local_classes:
            local_classes.append(rem_cls)
            class_idx = len(local_classes) - 1
            remote_class_num_mapping[idx] = class_idx

    return local_classes, remote_class_num_mapping


def _filter_metadata_keys(keys: Iterable[str]) -> list[str]:
    # TODO: Make this better somehow
    KEYS_TO_IGNORE = REQUIRED_METADATA_FIELD_NAMES + REQUIRED_METADATA_IMPORT_COLS + METADATA_FIELDS_TO_STRIP
    return [k for k in keys if k not in KEYS_TO_IGNORE]


def _add_common_metadata_fields(local_meta_records: list[dict[str, str]], remote_meta_records: list[dict[str, str]]):
    have_local = len(local_meta_records) > 0
    have_remote = len(remote_meta_records) > 0

    if have_local and have_remote:
        local_keys = _filter_metadata_keys(local_meta_records[0].keys())
        remote_keys = _filter_metadata_keys(remote_meta_records[0].keys())
        return [k for k in local_keys if k in remote_keys]
    else:   # Need both to have common keys!
        return []


def _add_all_metadata_fields(local_meta_records: list[dict[str, str]], remote_meta_records: list[dict[str, str]]):
    have_local = len(local_meta_records) > 0
    have_remote = len(remote_meta_records) > 0

    ret = []

    if not have_local and not have_remote:
        pass
    elif not have_local:
        ret = _filter_metadata_keys(remote_meta_records[0].keys())
    elif not have_remote:
        ret = _filter_metadata_keys(local_meta_records[0].keys())
    else:   # Have both
        local_keys = _filter_metadata_keys(local_meta_records[0].keys())
        remote_keys = _filter_metadata_keys(remote_meta_records[0].keys())
        ret += local_keys
        ret += [k for k in remote_keys if k not in local_keys]

    return ret


def _add_fields(entry: dict[str, Any], fieldnames: list[str]):
    for f in fieldnames:
        entry.setdefault(f, None)

    for f in METADATA_FIELDS_TO_STRIP:
        entry.pop(f, None)

    return entry


def _merge_metadata(local_dataset: SeraphDataset,
                    remote_dataset: SeraphDataset,
                    metadata_field_merge_strat: MetadataFieldMergeStrategy,
                    class_list: list[str],
                    remote_class_mapping: dict[int, int],
                    ):
    _, local_meta_records = local_dataset.get_metadata()
    _, remote_meta_records = remote_dataset.get_metadata()

    remote_seraph = remote_dataset.get_seraph_metadata()
    original_dataset_uri = remote_seraph.uri
    license = remote_seraph.license

    for entry in remote_meta_records:
        entry["original_dataset_uri"] = original_dataset_uri
        entry.setdefault("license", license or "UNKNOWN")

        # If no local metadata, the result will be the same as the remote data so skip this step
        if local_meta_records:
            original_class_id = int(entry["class_id"])
            new_class_id = remote_class_mapping.get(original_class_id, class_list.index(entry["class_name"]))

            entry["class_id"] = str(new_class_id)
            entry["class_name"] = class_list[new_class_id]

    fieldnames = REQUIRED_METADATA_FIELD_NAMES + REQUIRED_METADATA_IMPORT_COLS
    if metadata_field_merge_strat == MetadataFieldMergeStrategy.APPEND:
        fieldnames += _add_all_metadata_fields(local_meta_records, remote_meta_records)
    elif metadata_field_merge_strat == MetadataFieldMergeStrategy.TRUNCATE:
        fieldnames += _add_common_metadata_fields(local_meta_records, remote_meta_records)
    else:
        raise ValueError(metadata_field_merge_strat)

    for entry in local_meta_records:
        _add_fields(entry, fieldnames)

    for entry in remote_meta_records:
        _add_fields(entry, fieldnames)

    return fieldnames, local_meta_records, remote_meta_records


# TODO: Support more than `audio/wav`
def _rewrite_audio_file(fq_input_name: str,
                        fq_output_name: str,
                        *,
                        target_sr: Optional[int] = None,
                        target_channels: Optional[int] = None,
                        ):
    # Faster to copy with system commands than torchaudio, so see if that's possible
    if target_sr is None and target_channels is None:
        use_shell_copy = True
    else:
        audio_metadata = TinyTag.get(fq_input_name)
        sr_matches = target_sr is None or (audio_metadata.samplerate == target_sr)
        channels_match = target_channels is None or (audio_metadata.channels == target_channels)
        use_shell_copy = (sr_matches and channels_match)

    if use_shell_copy:
        if fq_input_name != fq_output_name:
            shutil.copy(fq_input_name, fq_output_name)
        return

    wave, sr = torchaudio.load(fq_input_name, normalize=True)

    # Resample
    final_sr = target_sr or sr

    if target_sr is not None:
        if target_sr > sr:
            raise ValueError(f"Cannot safely upsample file {fq_input_name} from {sr} to {target_sr}")
        elif target_sr != sr:
            wave = torchaudio.functional.resample(wave, orig_freq=sr, new_freq=target_sr)

    # Channels
    num_channels = wave.size(0)
    if target_channels is not None:
        if target_channels > num_channels:
            raise ValueError(f"Cannot safely add channels to file {fq_input_name} from {num_channels} to {target_channels}")
        elif num_channels != target_channels:
            if target_channels != 1:
                raise NotImplementedError("For now, only converting channels to mono is supported")
            else:
                wave = torch.mean(wave, dim=0, keepdim=True)

    # Save the file
    # TODO: Honor encoding and bits/sample from `seraph.json`
    torchaudio.save(fq_output_name, wave, sample_rate=final_sr, encoding="PCM_S", bits_per_sample=16)


def _combine_audio_data_files(local_dataset: SeraphDataset,
                              remote_dataset: SeraphDataset,
                              local_meta_records: list[dict[str, str]],
                              remote_meta_records: list[dict[str, str]],
                              *,
                              channels_to_mix_to=None,
                              mix_local_channels=False,
                              sr_to_mix_to=None,
                              mix_local_sr=False,
                              ):
    local_data_dir = local_dataset.get_data_dir()
    remote_data_dir = remote_dataset.get_data_dir()

    if mix_local_channels or mix_local_sr:
        for entry in tqdm(local_meta_records, "Re-mixing local files"):
            filename = entry["filename"]
            fq_filename = os.path.join(local_data_dir, filename)
            _rewrite_audio_file(fq_filename, fq_filename, target_sr=sr_to_mix_to, target_channels=channels_to_mix_to)

    for entry in tqdm(remote_meta_records, "Importing remote files"):
        filename = entry["filename"]
        fq_input_name = os.path.join(remote_data_dir, filename)
        fq_output_name = os.path.join(local_data_dir, filename)
        _rewrite_audio_file(fq_input_name, fq_output_name, target_sr=sr_to_mix_to, target_channels=channels_to_mix_to)


def _import_audio_dataset(local_dataset: SeraphDataset,
                          remote_dataset: SeraphDataset,
                          metadata_field_merge_strat: MetadataFieldMergeStrategy,
                          media_subtype_merge_strat: AudioBaseMergeStrategy,    # noqa
                          channel_merge_strat: AudioMixMergeStrategy,
                          sample_rate_merge_strat: AudioMixMergeStrategy,
                          subtype_value_merge_strat: AudioBaseMergeStrategy,
                          class_select: Optional[list[str]],
                          class_exclude: Optional[list[str]],
                          split_select: Optional[str],
                          fold_select: Optional[str],
                          min_length_secs: Optional[int],
                          duration_col_name: Optional[str],
                          ):
    ####################
    # Get local and remote metadata
    ####################
    local_seraph = local_dataset.get_seraph_metadata()
    remote_seraph = remote_dataset.get_seraph_metadata()

    # TODO: support more than just audio/wav
    local_seraph.mediaMetadata = local_seraph.mediaMetadata or {}
    local_seraph.mediaMetadata.setdefault("audio", {})
    local_seraph.mediaMetadata["audio"].setdefault("wav", {})

    has_remote_media_metadata = remote_seraph.mediaMetadata and remote_seraph.mediaMetadata.get("audio", {}).get("wav", None)
    if not has_remote_media_metadata:
        raise NotImplementedError("For now, the remote dataset needs to have `mediaMetadata` for `audio/wav`")

    ####################
    # Media Subtypes
    # TODO: Support multiple media subtypes
    ####################
    if not local_seraph.mediaSubtype or not remote_seraph.mediaSubtype:
        raise NotImplementedError("For now, you need to submit a media subtype for both datasets")
    elif local_seraph.mediaType != remote_seraph.mediaType:
        raise NotImplementedError("For now, media types must match between datasets")
    elif local_seraph.mediaSubtype != remote_seraph.mediaSubtype:
        raise NotImplementedError("For now, media subtypes must match between datasets")
    elif local_seraph.mediaType != SupportedMediaType.AUDIO or local_seraph.mediaSubtype != "wav":
        raise NotImplementedError("For now, only `audio/wav` datasets are supported")

    ####################
    # Channels
    # TODO: support more than just audio/wav
    ####################
    channels_to_mix_to = None
    mix_local_channels = False

    local_channels = local_seraph.mediaMetadata["audio"]["wav"].get("numChannels", None)
    remote_channels = remote_seraph.mediaMetadata["audio"]["wav"].get("numChannels", None)  # type: ignore

    if not remote_channels:
        raise NotImplementedError("For now, the remote dataset needs to have a number of channels set")
    elif local_channels and local_channels != remote_channels:
        if channel_merge_strat == AudioMixMergeStrategy.REJECT:
            raise ValueError(f"Audio channel numbers must match but are {local_channels} vs. {remote_channels}")
        elif channel_merge_strat == AudioMixMergeStrategy.PUSH_DOWN:
            raise NotImplementedError("For now, PUSH_DOWN is not supported for channel mismatches")
        else:
            channels_to_mix_to = min(local_channels, remote_channels)
            mix_local_channels = local_channels > remote_channels
    else:
        local_seraph.mediaMetadata["audio"]["wav"]["numChannels"] = remote_channels

    ####################
    # Sample rates
    # TODO: support more than just audio/wav
    ####################
    sr_to_mix_to = None
    mix_local_sr = False

    local_sr = local_seraph.mediaMetadata["audio"]["wav"].get("sampleRate", None)
    remote_sr = remote_seraph.mediaMetadata["audio"]["wav"].get("sampleRate", None)  # type: ignore

    if not remote_sr:
        raise NotImplementedError("For now, the remote dataset needs to have a sample rate set")
    elif local_sr and local_sr != remote_sr:
        if sample_rate_merge_strat == AudioMixMergeStrategy.REJECT:
            raise ValueError(f"Sample rates must match but are {local_sr} vs. {remote_sr}")
        elif sample_rate_merge_strat == AudioMixMergeStrategy.PUSH_DOWN:
            raise NotImplementedError("For now, PUSH_DOWN is not supported for sample rate mismatches")
        else:
            sr_to_mix_to = min(local_sr, remote_sr)
            mix_local_sr = local_sr > remote_sr
    else:
        local_seraph.mediaMetadata["audio"]["wav"]["sampleRate"] = remote_sr

    ####################
    # Subtype values
    # TODO: support more than just audio/wav
    ####################
    KEYS_TO_SKIP = ["numChannels", "sampleRate"]
    local_keys = [k for k in local_seraph.mediaMetadata["audio"]["wav"].keys() if k not in KEYS_TO_SKIP]
    remote_keys = [k for k in remote_seraph.mediaMetadata["audio"]["wav"].keys() if k not in KEYS_TO_SKIP]  # type: ignore

    for k in local_keys:
        local_val = local_seraph.mediaMetadata["audio"]["wav"][k]
        remote_val = remote_seraph.mediaMetadata["audio"]["wav"].get(k, None)  # type: ignore

        if local_val != remote_val:
            if subtype_value_merge_strat == AudioBaseMergeStrategy.REJECT:
                raise ValueError(f"Subtype value mismatch: {local_val} vs. {remote_val}")
            elif subtype_value_merge_strat == AudioBaseMergeStrategy.PUSH_DOWN:
                raise NotImplementedError("For now, PUSH_DOWN is not supported for subtype value mismatches")

    for k in remote_keys:
        local_val = local_seraph.mediaMetadata["audio"]["wav"].get(k, None)
        remote_val = remote_seraph.mediaMetadata["audio"]["wav"][k]  # type: ignore

        if local_val and local_val != remote_val:
            if subtype_value_merge_strat == AudioBaseMergeStrategy.REJECT:
                raise ValueError(f"Subtype value mismatch: {local_val} vs. {remote_val}")
            elif subtype_value_merge_strat == AudioBaseMergeStrategy.PUSH_DOWN:
                raise NotImplementedError("For now, PUSH_DOWN is not supported for subtype value mismatches")
        else:
            local_seraph.mediaMetadata["audio"]["wav"][k] = remote_val

    ####################
    # Actually import the data
    ####################
    imported_classes = _prune_remote_data(remote_dataset, class_select, class_exclude, split_select, fold_select, min_length_secs, duration_col_name)

    new_class_list, remote_class_mapping = _merge_classes(local_dataset, remote_dataset)
    fieldnames, local_meta_records, remote_meta_records = _merge_metadata(local_dataset, remote_dataset, metadata_field_merge_strat, new_class_list, remote_class_mapping)
    _combine_audio_data_files(local_dataset,
                              remote_dataset,
                              local_meta_records,
                              remote_meta_records,
                              channels_to_mix_to=channels_to_mix_to,
                              mix_local_channels=mix_local_channels,
                              sr_to_mix_to=sr_to_mix_to,
                              mix_local_sr=mix_local_sr,
                              )

    ####################
    # Save the dataset
    ####################
    remote_meta = remote_dataset.get_seraph_metadata()

    change = ChangeRecord(
        bump_type=VersionBumpType.MAJOR,
        change_type=ChangeType.ADD,
        message=f"Added data from {remote_meta.uri} to dataset",
        is_import=True,
    )
    import_rec = ImportRecord(
        uri=remote_meta.uri,
        version=remote_meta.version,
        name=remote_meta.name,
        classes=imported_classes,
    )

    local_dataset.set_multiple(classes=new_class_list,
                               metadata_headers=fieldnames,
                               metadata_records=local_meta_records + remote_meta_records,
                               seraph_metadata=local_seraph,
                               change_records=[change],
                               import_records=[import_rec])
    local_dataset.save()


def _write_audio_clips(record: FileToClip, data_dir: str):
    fq_input_filename = os.path.join(data_dir, record.filename)
    audio, sr = torchaudio.load(fq_input_filename, normalize=True)

    if len(record.clips) == 1:
        fq_output_filename = os.path.join(data_dir, record.clips[0].clip_filename)
        os.rename(fq_input_filename, fq_output_filename)
        return

    for clip in record.clips:
        fq_output_filename = os.path.join(data_dir, clip.clip_filename)
        start_frame = int(clip.start_secs * sr)
        end_frame = int(clip.end_secs * sr)
        new_wav = audio[:, start_frame:end_frame]

        # TODO: Honor formats from `seraph.json` metadata
        torchaudio.save(fq_output_filename, new_wav, sr, encoding="PCM_S", bits_per_sample=16)

    os.unlink(fq_input_filename)


def _clip_audio_files(dataset: SeraphDataset,
                      clip_duration_secs: float,
                      duration_col_name: str,
                      end_strat: ClipEndStrategy,
                      force: bool,
                      dry_run: bool,
                      ):
    data_dir = dataset.get_data_dir()
    headers, metadata_records = dataset.get_metadata()

    have_duration_column = False
    for h in headers:
        if h == duration_col_name:
            have_duration_column = True
        elif h.lower().startswith("clip"):
            message = f"Possible clip column found: {h}"
            if force:
                warnings.warn(message)
            else:
                raise ValueError(message)
        elif h.lower().startswith("segment"):
            message = f"Possible segment column found: {h}"
            if force:
                warnings.warn(message)
            else:
                raise ValueError(message)

    if not have_duration_column:
        raise ValueError("No duration column found")

    CLIP_HEADERS_TO_ADD = ["file_id", "clip_id"]
    for h in CLIP_HEADERS_TO_ADD:
        if h not in headers:
            headers.append(h)

    # Do the clipping
    clipped_metadata = []
    files_to_clip: list[FileToClip] = []

    for record in metadata_records:
        original_duration = float(record[duration_col_name])

        duration = original_duration
        original_filename = record["filename"]

        filename_segs = original_filename.split(".")
        filename_root = ".".join(filename_segs[:-1])
        ext = filename_segs[-1]

        clip_record = FileToClip(filename=original_filename, clips=[])
        clip_id = 0
        start_offset_secs = 0.0

        while duration >= clip_duration_secs:
            clip_filename = f"{filename_root}-{clip_id}.{ext}"

            # Update metadata records
            clip_meta = deepcopy(record)
            clip_meta[duration_col_name] = str(clip_duration_secs)
            clip_meta["filename"] = clip_filename
            clip_meta["file_id"] = original_filename
            clip_meta["clip_id"] = str(clip_id)
            clipped_metadata.append(clip_meta)

            # Assemble necessary fields for subsequent file clipping
            end_offset_secs = start_offset_secs + clip_duration_secs
            clip_record.clips.append(Clip(
                clip_filename=clip_filename,
                start_secs=start_offset_secs,
                end_secs=end_offset_secs,
            ))

            # Update loop conditions
            start_offset_secs = end_offset_secs
            clip_id += 1
            duration -= clip_duration_secs

        have_clips = len(clip_record.clips) > 0

        if end_strat == ClipEndStrategy.EXTEND and have_clips:
            clipped_metadata[-1][duration_col_name] = clip_duration_secs + duration
            clip_record.clips[-1].end_secs += duration
        elif end_strat == ClipEndStrategy.PARTIAL or not have_clips:  # Possible TODO: Clean up this path
            clip_filename = f"{filename_root}-{clip_id}.{ext}"

            # Update metadata records
            clip_meta = deepcopy(record)
            clip_meta[duration_col_name] = str(duration)
            clip_meta["filename"] = clip_filename
            clip_meta["file_id"] = original_filename
            clip_meta["clip_id"] = str(clip_id)
            clipped_metadata.append(clip_meta)

            # Assemble necessary fields for subsequent file clipping
            end_offset_secs = start_offset_secs + clip_duration_secs
            clip_record.clips.append(Clip(
                clip_filename=clip_filename,
                start_secs=start_offset_secs,
                end_secs=end_offset_secs,
            ))
        else:   # ClipEndStrategy.DISCARD
            pass

        files_to_clip.append(clip_record)

    if not dry_run:
        # Update the files
        for record in tqdm(files_to_clip, "Clipping audio files"):
            _write_audio_clips(record, data_dir)

        # Save the dataset
        change = ChangeRecord(
            bump_type=VersionBumpType.MINOR,
            change_type=ChangeType.CHANGE,
            message=f"Clipped audio to {clip_duration_secs:.02f} secs",
        )
        dataset.set_metadata_headers(headers, change_record=change).set_metadata_records(clipped_metadata).save()
    else:
        write_csv("clipped_metadata.csv", headers, clipped_metadata)


def _check_has_audio(fq_filename: str):
    wave, sr = torchaudio.load(fq_filename)

    # Mel Spectrogram
    mel_spec = torchaudio.transforms.MelSpectrogram(
        sample_rate=sr,
        n_fft=1024,
        n_mels=128,
        hop_length=512,
        normalized=False,
    )
    mel_output = mel_spec(wave).squeeze()
    log_mel_output = torchaudio.transforms.AmplitudeToDB(top_db=80)(mel_output)

    # Check spectrogram
    min_in_val = torch.min(log_mel_output).item()
    max_in_val = torch.max(log_mel_output).item()
    in_span = max_in_val - min_in_val
    return in_span != 0


def _fmt_col(val: str | bool | None | int):
    if val is None or (isinstance(val, str) and not val):
        return "-"
    elif not val:
        return str(val)
    else:
        return f"[red]{val}[/red]"


###############################################################################
# ! Commands
###############################################################################
@click.group("audio", help="Commands for importing, modifying, and pruning audio data")
def audio():
    pass


@audio.command("import", help="Import audio data from an external Seraph dataset")
@click.option("--dataset_dir", "-d", default=".")
@click.option("--import_dir", "-i", required=True, help="The directory from which to import data")
@click.option("--metadata_field_merge_strat", default="append", type=click.Choice(METADATA_FIELD_MERGE_STRATEGIES), help="What should be done with unmatched metadata columns?")
@click.option("--media_subtype_merge_strat", default="reject", type=click.Choice(AUDIO_BASE_MERGE_STRATEGIES), help="What should be done if the audio subtypes differ between datasets?")
@click.option("--channel_merge_strat", default="reject", type=click.Choice(AUDIO_MIX_MERGE_STRATEGIES), help="What should be done if the number of audio channels differ between datasets?")
@click.option("--sample_rate_merge_strat", default="reject", type=click.Choice(AUDIO_MIX_MERGE_STRATEGIES), help="What should be done if the sample rate of audio files differ between datasets?")
@click.option("--subtype_value_merge_strat", default="reject", type=click.Choice(AUDIO_BASE_MERGE_STRATEGIES), help="What should be done if misc subtype values differ between datasets?")
@click.option("--class_select", multiple=True, help="One or more classes to cherry-pick from the remote dataset")
@click.option("--class_exclude", multiple=True, help="One or more classes from the remote dataset to exclude")
@click.option("--split_select", help="At most one split to import to the exclusion of others")
@click.option("--fold_select", help="At most one fold to import to the exclusion of others")
@click.option("--min_length_secs", type=int, help="Files from the import dataset less than this value will be ignored")
@click.option("--duration_col_name", default=DURATION_COL_DEFAULT_NAME, help="This parameter has no effect if `min_length_secs` is not set")
def audio_import(dataset_dir: str,
                 import_dir: str,
                 metadata_field_merge_strat: str,
                 media_subtype_merge_strat: str,
                 channel_merge_strat: str,
                 sample_rate_merge_strat: str,
                 subtype_value_merge_strat: str,
                 class_select: tuple[str],
                 class_exclude: tuple[str],
                 split_select: Optional[str],
                 fold_select: Optional[str],
                 min_length_secs: Optional[int],
                 duration_col_name: str,
                 ):
    local_dataset = SeraphDataset(dataset_dir)
    remote_dataset = SeraphDataset(import_dir)

    metadata_field_merge_strat_fmt = str_to_enum(metadata_field_merge_strat, MetadataFieldMergeStrategy)
    media_subtype_merge_strat_fmt = str_to_enum(media_subtype_merge_strat, AudioBaseMergeStrategy)
    channel_merge_strat_fmt = str_to_enum(channel_merge_strat, AudioMixMergeStrategy)
    sample_rate_merge_strat_fmt = str_to_enum(sample_rate_merge_strat, AudioMixMergeStrategy)
    subtype_value_merge_strat_fmt = str_to_enum(subtype_value_merge_strat, AudioBaseMergeStrategy)

    if class_select and class_exclude:
        raise ValueError("You cannot exclude and cherry-pick classes at the same time")
    elif min_length_secs is not None and min_length_secs < 1:
        raise ValueError("Paramater `min_length_secs` must be a positive integer if specified")

    if split_select and fold_select:
        raise ValueError("You cannot select a split and a fold at the same time")
    elif fold_select:
        try:
            int(fold_select)
        except ValueError:
            raise ValueError(f"Invalid fold: {fold_select}")
    elif split_select and split_select not in ["train", "val", "test"]:
        raise ValueError(f"Invalid split: {split_select}")

    _import_audio_dataset(local_dataset,
                          remote_dataset,
                          metadata_field_merge_strat_fmt,
                          media_subtype_merge_strat_fmt,
                          channel_merge_strat_fmt,
                          sample_rate_merge_strat_fmt,
                          subtype_value_merge_strat_fmt,
                          list(class_select) if class_select else None,
                          list(class_exclude) if class_exclude else None,
                          split_select,
                          fold_select,
                          min_length_secs,
                          duration_col_name if min_length_secs else None,
                          )


@audio.command("duration", help="Add a duration (secs) column to audio metadata")
@click.option("--dataset_dir", "-d", default=".")
@click.option("--metadata_column_conflict_strat", default="reject", type=click.Choice(METADATA_COLUMN_CONFLICT_STRATEGIES))
def audio_add_duration(dataset_dir: str,
                       metadata_column_conflict_strat: str,
                       ):
    dataset = SeraphDataset(dataset_dir)
    fieldnames, metadata = dataset.get_metadata()

    col_strat = str_to_enum(metadata_column_conflict_strat, MetadataColumnConflictStrategy)

    duration_cols = [f for f in fieldnames if f.startswith("duration")]
    if col_strat == MetadataColumnConflictStrategy.REJECT and len(duration_cols):
        raise ValueError(f"Rejecting due to conflict on one or more duration columns: {duration_cols}")
    elif col_strat == MetadataColumnConflictStrategy.KEEP and DURATION_COL_DEFAULT_NAME not in fieldnames:
        fieldnames.append(DURATION_COL_DEFAULT_NAME)
    elif col_strat == MetadataColumnConflictStrategy.REPLACE:
        fieldnames = [f for f in fieldnames if f not in duration_cols]
        fieldnames.append(DURATION_COL_DEFAULT_NAME)
    else:
        fieldnames.append(DURATION_COL_DEFAULT_NAME)

    data_dir = dataset.get_data_dir()
    for entry in tqdm(metadata, "Processing file durations"):
        filename = entry["filename"]
        fq_filename = os.path.join(data_dir, filename)
        tags = TinyTag.get(fq_filename)
        duration_secs = tags.duration

        if col_strat == MetadataColumnConflictStrategy.REPLACE:
            for c in duration_cols:
                del entry[c]

        entry[DURATION_COL_DEFAULT_NAME] = f"{duration_secs:.03f}"

    change = ChangeRecord(
        bump_type=VersionBumpType.MINOR,
        change_type=ChangeType.ADD,
        message="Added or updated audio duration column",
    )
    dataset.set_metadata_headers(fieldnames, change_record=change).set_metadata_records(metadata).save()


@audio.command("clip", help="Clip audio data to a specified length (in secs) and update metadata")
@click.option("--dataset_dir", "-d", default=".")
@click.option("--clip_duration_secs", type=float, required=True)
@click.option("--duration_col_name", default=DURATION_COL_DEFAULT_NAME)
@click.option("--clip_end_strategy", default="extend", type=click.Choice(CLIP_END_STRAEGIES), help="If a duration is not evenly divisible by clip_duration_secs, what happens to the last clip?")
@click.option("--force", is_flag=True, help="If not provided, will fail to clip audio that appears to have already been clipped")
@click.option("--dry_run", is_flag=True)
def audio_clip_files(dataset_dir: str,
                     clip_duration_secs: float,
                     duration_col_name: str,
                     clip_end_strategy: str,
                     force: bool,
                     dry_run: bool,
                     ):
    end_strat = str_to_enum(clip_end_strategy, ClipEndStrategy)

    dataset = SeraphDataset(dataset_dir)

    _clip_audio_files(dataset, clip_duration_secs, duration_col_name, end_strat, force, dry_run)


@audio.command("resample", help="Resample an entire audio dataset to a single sample rate")
@click.option("--dataset_dir", "-d", default=".")
@click.option("--target_sr", type=int, required=True, help="In Hz, must NOT be higher than the lowest sample rate of the dataset")
def audio_resample(dataset_dir: str, target_sr: int):
    dataset = SeraphDataset(dataset_dir)

    data_dir = dataset.get_data_dir()
    _, meta_records = dataset.get_metadata()
    seraph = dataset.get_seraph_metadata()
    if not seraph.mediaMetadata:
        raise SeraphMetadataError(f"No media metadata found for dataset {seraph.name}")

    for entry in tqdm(meta_records, "Mixing audio files"):
        filename = entry["filename"]
        fq_filename = os.path.join(data_dir, filename)

        # TODO: Support additional channels, maybe
        _rewrite_audio_file(fq_filename, fq_filename, target_sr=target_sr, target_channels=1)

    # Update metadata
    seraph.mediaMetadata["audio"]["wav"]["sampleRate"] = target_sr
    seraph.mediaMetadata["audio"]["wav"]["numChannels"] = 1

    # Save the updates
    change = ChangeRecord(
        bump_type=VersionBumpType.MAJOR,
        change_type=ChangeType.CHANGE,
        message=f"Resampled audio to {(target_sr/1000):.02f} KHz",
    )
    dataset.set_seraph_metadata(seraph, change_record=change).save()


# TODO: Support more than just lossless audio and use the expected metadata to drive the logic
@audio.command("verify", help="Verify that every file in the dataset conforms to the proper media metadata contract")
@click.option("--dataset_dir", "-d", default=".")
@click.option("--output_format", "-o", default="print", type=click.Choice(VERIFY_OUTPUT_FORMATS))
@click.option("--check_file_len", is_flag=True, help="Warn of files with no audio length")
@click.option("--check_has_data", is_flag=True, help="Warn of files with no audio data (i.e., silence)")
def audio_verify(dataset_dir: str, output_format: str, check_file_len: bool, check_has_data: bool):
    dataset = SeraphDataset(dataset_dir)

    seraph = dataset.get_seraph_metadata()
    if seraph.mediaMetadata is None or seraph.mediaMetadata["audio"] is None:
        print("Audio verification requires the 'audio' field of the 'mediaMetadata' to be present")
        sys.exit(1)
    audio_meta = seraph.mediaMetadata["audio"]

    fmt = str_to_enum(output_format, VerifyOutputFormat)

    data_dir = dataset.get_data_dir()
    files = os.listdir(data_dir)

    violations: list[VerifyError] = []

    for f in tqdm(files, "Scanning for dataset contract violations"):
        violation = VerifyError(filename=f, subtype=None, sample_rate=None, channels=None, bit_depth=None, is_empty=False, no_audio=False)

        ext = f.split(".")[-1]
        expected_meta = audio_meta.get(ext, None)
        if expected_meta is None:
            violation.subtype = ext
            continue

        fq_filename = os.path.join(data_dir, f)
        file_meta = TinyTag.get(fq_filename)

        if expected_meta["sampleRate"] != file_meta.samplerate:
            violation.sample_rate = file_meta.samplerate

        if expected_meta["numChannels"] != file_meta.channels:
            violation.channels = file_meta.channels

        if expected_meta["bitsPerSample"] != file_meta.bitdepth:
            violation.bit_depth = file_meta.bitdepth

        if check_file_len and (file_meta.duration is None or file_meta.duration < 0.01):
            violation.is_empty = True

        if check_has_data and not _check_has_audio(fq_filename):
            violation.no_audio = True

        if violation.has_violation():
            violations.append(violation)

    if not violations:
        print("[bold green]No dataset contract violations![bold green]")
    else:
        COLUMNS = ["filename", "subtype", "sample_rate", "channels", "bit_depth", "is_empty", "no_audio"]
        if fmt == VerifyOutputFormat.CSV:
            write_csv(os.path.join(dataset_dir, "verification-errors.csv"),
                      COLUMNS,
                      [asdict(v) for v in violations])
        elif fmt == VerifyOutputFormat.JSON:
            output = [asdict(v) for v in violations]
            write_json(os.path.join(dataset_dir, "verification-errors.json"), output)
        else:
            table = Table(
                *COLUMNS,
                title=f"Dataset Contract Violations ({len(violations)})"
            )

            for v in violations:
                table.add_row(v.filename, _fmt_col(v.subtype), _fmt_col(v.sample_rate), _fmt_col(v.channels), _fmt_col(v.bit_depth), _fmt_col(v.is_empty), _fmt_col(v.no_audio))
            print(table)


@audio.command("prune", help="Remove silent and/or empty audio files from the dataset")
@click.option("--dataset_dir", "-d", default=".")
@click.option("--remove_zero_len", is_flag=True, help="Remove files with duration of 0 sec")
@click.option("--remove_silence", is_flag=True, help="Remove files that contain only silence")
def audio_prune(dataset_dir: str, remove_zero_len: bool, remove_silence: bool):
    dataset = SeraphDataset(dataset_dir)
    data_dir = dataset.get_data_dir()
    _, original_metadata_records = dataset.get_metadata()

    if not remove_zero_len and not remove_silence:
        print("[red]You must specify at least one removal parameter: `remove_zero_len`, `remove_silence`[/red]")
        sys.exit(1)

    new_metadata_records = []

    for record in tqdm(original_metadata_records, "Pruning audio files"):
        filename = record["filename"]
        fq_filename = os.path.join(data_dir, filename)
        file_meta = TinyTag.get(fq_filename)

        is_zero_len = remove_zero_len and (file_meta.duration is None or file_meta.duration < 0.01)
        is_silence = remove_silence and not _check_has_audio(fq_filename)

        if is_zero_len or is_silence:
            os.unlink(fq_filename)
        else:
            new_metadata_records.append(record)

    delta = len(original_metadata_records) - len(new_metadata_records)
    if delta != 0:
        change = ChangeRecord(
            bump_type=VersionBumpType.PATCH,
            change_type=ChangeType.REMOVE,
            message=f"Pruned {delta} records without audio data",
        )
        dataset.set_metadata_records(new_metadata_records, change_record=change).save()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    audio()
