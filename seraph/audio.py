###############################################################################
# Global Imports
###############################################################################
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import os
import shutil
from typing import Any, Optional
import warnings


###############################################################################
# 3PP Imports
###############################################################################
import click
from tqdm import tqdm
from tinytag import TinyTag
import torch
import torchaudio


###############################################################################
# Local Imports
###############################################################################
from .common import REQUIRED_METADATA_FIELD_NAMES, str_to_enum, write_csv
from .dataset import SeraphDataset
from .provenance import ProvenanceActivityType, mark_provenance
from .version import mark_version_note, VersionBumpType, ChangeType


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


###############################################################################
# Constants
###############################################################################
METADATA_FIELDS_TO_STRIP = ["sample_rate", "num_channels"]
DURATION_COL_DEFAULT_NAME = "duration_secs"


###############################################################################
# Helpers
###############################################################################
def _prune_remote_data_by_classes(remote_dataset: SeraphDataset,
                                  class_select: Optional[list[str]],
                                  class_exclude: Optional[list[str]],
                                  ):
    # Nothing to be done, so bail out
    if not class_select and not class_exclude:
        return

    # These are mutually exclusive
    if class_select:
        select_fn = lambda cls: (cls in class_select)       # noqa
    else:
        select_fn = lambda cls: (cls not in class_exclude)  # noqa

    classes = remote_dataset.get_classes()
    _, metadata_records = remote_dataset.get_metadata()

    new_classes = [c for c in classes if select_fn(c)]
    new_metadata = [m for m in metadata_records if select_fn(m["class_name"])]

    remote_dataset.set_classes(new_classes).set_metadata_records(new_metadata)


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
    KEYS_TO_IGNORE = REQUIRED_METADATA_FIELD_NAMES + METADATA_FIELDS_TO_STRIP
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

    # If no local metadata, the result will be the same as the remote data so skip this step
    if local_meta_records:
        for entry in remote_meta_records:
            original_class_id = int(entry["class_id"])
            new_class_id = remote_class_mapping.get(original_class_id, class_list.index(entry["class_name"]))

            entry["class_id"] = str(new_class_id)
            entry["class_name"] = class_list[new_class_id]

    fieldnames = deepcopy(REQUIRED_METADATA_FIELD_NAMES)
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
    if not local_seraph.mediaType or not remote_seraph.mediaType:
        raise NotImplementedError("For now, you need to submit a media type for both datasets")
    elif not local_seraph.mediaSubtype or not remote_seraph.mediaSubtype:
        raise NotImplementedError("For now, you need to submit a media subtype for both datasets")
    elif local_seraph.mediaType != remote_seraph.mediaType:
        raise NotImplementedError("For now, media types must match between datasets")
    elif local_seraph.mediaSubtype != remote_seraph.mediaSubtype:
        raise NotImplementedError("For now, media subtypes must match between datasets")
    elif local_seraph.mediaType != "audio" or local_seraph.mediaSubtype != "wav":
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
    _prune_remote_data_by_classes(remote_dataset, class_select, class_exclude)

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
    local_dataset.set_multiple(classes=new_class_list,
                               metadata_headers=fieldnames,
                               metadata_records=local_meta_records + remote_meta_records,
                               seraph_metadata=local_seraph)
    local_dataset.save()


def _write_audio_clips(record: FileToClip, data_dir: str):
    fq_input_filename = os.path.join(data_dir, record.filename)
    audio, sr = torchaudio.load(fq_input_filename, normalize=True)

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

    headers.append("file_id")
    headers.append("clip_id")

    # Do the clipping
    clipped_metadata = []
    files_to_clip: list[FileToClip] = []

    for record in metadata_records:
        original_duration = float(record["duration_secs"])

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
            clip_meta["duration_secs"] = str(clip_duration_secs)
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

        if end_strat == ClipEndStrategy.EXTEND:
            clipped_metadata[-1]["duration_secs"] = clip_duration_secs + duration
            clip_record.clips[-1].end_secs += duration
        elif end_strat == ClipEndStrategy.PARTIAL:  # Possible TODO: Clean up this path
            clip_filename = f"{filename_root}-{clip_id}.{ext}"

            # Update metadata records
            clip_meta = deepcopy(record)
            clip_meta["duration_secs"] = str(duration)
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
        dataset.set_metadata_headers(headers).set_metadata_records(clipped_metadata).save()
    else:
        write_csv("clipped_metadata.csv", headers, clipped_metadata)


###############################################################################
# ! Commands
###############################################################################
@click.group("audio")
def audio():
    pass


@audio.command("import")
@click.option("--import_dir", required=True)
@click.option("--metadata_field_merge_strat", default="append", type=click.Choice(METADATA_FIELD_MERGE_STRATEGIES))
@click.option("--media_subtype_merge_strat", default="reject", type=click.Choice(AUDIO_BASE_MERGE_STRATEGIES))
@click.option("--channel_merge_strat", default="reject", type=click.Choice(AUDIO_MIX_MERGE_STRATEGIES))
@click.option("--sample_rate_merge_strat", default="reject", type=click.Choice(AUDIO_MIX_MERGE_STRATEGIES))
@click.option("--subtype_value_merge_strat", default="reject", type=click.Choice(AUDIO_BASE_MERGE_STRATEGIES))
@click.option("--class_select", multiple=True)
@click.option("--class_exclude", multiple=True)
def audio_import(import_dir: str,
                 metadata_field_merge_strat: str,
                 media_subtype_merge_strat: str,
                 channel_merge_strat: str,
                 sample_rate_merge_strat: str,
                 subtype_value_merge_strat: str,
                 class_select: tuple[str],
                 class_exclude: tuple[str],
                 ):
    local_dataset = SeraphDataset(".")
    remote_dataset = SeraphDataset(import_dir)

    metadata_field_merge_strat_fmt = str_to_enum(metadata_field_merge_strat, MetadataFieldMergeStrategy)
    media_subtype_merge_strat_fmt = str_to_enum(media_subtype_merge_strat, AudioBaseMergeStrategy)
    channel_merge_strat_fmt = str_to_enum(channel_merge_strat, AudioMixMergeStrategy)
    sample_rate_merge_strat_fmt = str_to_enum(sample_rate_merge_strat, AudioMixMergeStrategy)
    subtype_value_merge_strat_fmt = str_to_enum(subtype_value_merge_strat, AudioBaseMergeStrategy)

    if class_select and class_exclude:
        raise ValueError("You cannot exclude and cherry-pick classes at the same time")

    _import_audio_dataset(local_dataset,
                          remote_dataset,
                          metadata_field_merge_strat_fmt,
                          media_subtype_merge_strat_fmt,
                          channel_merge_strat_fmt,
                          sample_rate_merge_strat_fmt,
                          subtype_value_merge_strat_fmt,
                          list(class_select) if class_select else None,
                          list(class_exclude) if class_exclude else None,
                          )

    # Provenance
    remote_uri = remote_dataset.get_seraph_metadata().uri

    if local_dataset.track_provenance():
        mark_provenance(ProvenanceActivityType.USED, remote_uri, local_dataset.get_dataset_root_dir())

    if local_dataset.track_version():
        mark_version_note(VersionBumpType.MAJOR, ChangeType.ADD, f"Added data from {remote_uri} to dataset")


@audio.command("duration")
@click.option("--dataset_dir", default=".")
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

    dataset.set_metadata_headers(fieldnames).set_metadata_records(metadata).save()

    # Provenance
    if dataset.track_provenance():
        mark_provenance(ProvenanceActivityType.MODIFIED, "Added or updated audio duration column", dataset_dir)

    if dataset.track_version():
        mark_version_note(VersionBumpType.MINOR, ChangeType.ADD, "Added audio duration column", dataset_dir)


@audio.command("clip")
@click.option("--clip_duration_secs", type=float, required=True)
@click.option("--dataset_dir", default=".")
@click.option("--duration_col_name", default=DURATION_COL_DEFAULT_NAME)
@click.option("--clip_end_strategy", default="extend", type=click.Choice(CLIP_END_STRAEGIES), help="If a duration is not evenly divisible by clip_duration_secs, what happens to the last clip?")
@click.option("--force", is_flag=True)
@click.option("--dry_run", is_flag=True)
def audio_clip_files(clip_duration_secs: float,
                     dataset_dir: str,
                     duration_col_name: str,
                     clip_end_strategy: str,
                     force: bool,
                     dry_run: bool,
                     ):
    end_strat = str_to_enum(clip_end_strategy, ClipEndStrategy)

    dataset = SeraphDataset(dataset_dir)

    _clip_audio_files(dataset, clip_duration_secs, duration_col_name, end_strat, force, dry_run)

    # Data governance
    if not dry_run:
        gov_str = f"Clipped audio to {clip_duration_secs:.02f} secs"

        if dataset.track_provenance():
            mark_provenance(ProvenanceActivityType.MODIFIED, gov_str, dataset_dir)

        if dataset.track_version():
            mark_version_note(VersionBumpType.MINOR, ChangeType.CHANGE, gov_str)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    audio()
