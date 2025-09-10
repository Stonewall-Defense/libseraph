###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
from enum import Enum
import random
from typing import Any, Optional

###############################################################################
# 3PP Imports
###############################################################################
import click
from tqdm import tqdm

###############################################################################
# Local Imports
###############################################################################
from ..lib import str_to_enum, SeraphDataset, VersionBumpType, ChangeType, ChangeRecord


###############################################################################
# Types and Classes
###############################################################################
@dataclass
class SplitEntry:
    id: str
    data_count: float
    clips: list[dict[str, str]]


class MutableSlice:
    def __init__(self, baselist, begin, end=None):
        self._base = baselist
        self._begin = begin
        self._end = len(baselist) if end is None else end

    def __len__(self):
        return self._end - self._begin

    def __getitem__(self, i):
        return self._base[self._begin + i]

    def __setitem__(self, i, val):
        self._base[i + self._begin] = val


###############################################################################
# Enums
###############################################################################
class SplitChoice(Enum):
    _90_10 = "90_10"
    _80_20 = "80_20"
    _80_10_10 = "80_10_10"
    _60_10_10 = "60_20_20"


SPLIT_CHOICES = [val.value for val in SplitChoice]


###############################################################################
# Helpers
###############################################################################
def _shuffle_segments(sorted_lst: list[SplitEntry]):
    """
        Shuffle segments for a class where durations are equal.

        Folding code always orders largest to smallest duration, but
        the order of degenerate records is undefined.
    """
    start_idx = 0
    END = len(sorted_lst) - 1  # For ease of end of list
    while start_idx < END:
        curr_data_count = sorted_lst[start_idx].data_count
        next_idx = start_idx
        while sorted_lst[next_idx].data_count == curr_data_count and next_idx < END:
            next_idx += 1

        if next_idx != start_idx:
            slice_tmp = MutableSlice(sorted_lst, start_idx, next_idx)
            random.shuffle(slice_tmp)  # type: ignore

        start_idx = next_idx + 1

    return sorted_lst


def _preprocess_split_data(metadata: list[dict[str, str]],
                           len_col_name: Optional[str],
                           identity_col_name: str,
                           shuffle_segments: bool,
                           ):
    ret: dict[int, list[SplitEntry]] = {}

    for entry in tqdm(metadata, "Preprocessing metadata for splits"):
        class_id = int(entry["class_id"])

        # Default to count each item once for e.g. images
        data_count = float(entry[len_col_name]) if len_col_name else 1

        # Make sure the class is there, then check for a matching entry in that class
        ret.setdefault(class_id, [])
        idx = next((i for i, item in enumerate(ret[class_id]) if item.id == entry[identity_col_name]), None)

        # No match so add a new record
        if idx is None:
            ret[class_id].append(SplitEntry(id=entry[identity_col_name], data_count=data_count, clips=[entry]))
        # Match, so append to existing record
        else:
            ret[class_id][idx].data_count += data_count
            ret[class_id][idx].clips.append(entry)

    # Sort most data -> least
    for lst in ret.values():
        lst = sorted(lst, key=lambda x: (x.data_count), reverse=True)

        # Shuffle degenerate records (recommended)
        if shuffle_segments:
            lst = _shuffle_segments(lst)

    return ret


def _get_poorest_fold(duration_per_fold: list[float]) -> int:
    """Which fold for this class has the least total data currently?"""
    return duration_per_fold.index(min(duration_per_fold))


def _shuffle_together(lst1: list[Any], lst2: list[Any]) -> tuple[list[Any], list[Any]]:
    """Shuffle two lists but keep them in order relative to each other"""
    tmp = list(zip(lst1, lst2))
    random.shuffle(tmp)
    out1, out2 = zip(*tmp)
    return out1, out2  # type: ignore


def _fold_class(records: list[SplitEntry],
                *,
                num_folds=10,
                shuffle_folds=True,
                add_fold_id_to_clips=True,
                ):
    data_per_fold = [0.0] * num_folds
    folds = [[] for _ in range(num_folds)]

    for entry in records:
        data_count = entry.data_count
        poorest_fold = _get_poorest_fold(data_per_fold)

        if add_fold_id_to_clips:
            for clip in entry.clips:
                clip["fold"] = str(poorest_fold)

        data_per_fold[poorest_fold] += data_count
        folds[poorest_fold].append(entry)

    if shuffle_folds:
        return _shuffle_together(folds, data_per_fold)
    else:
        return folds, data_per_fold


def _make_ttv_split_params(split_choice: SplitChoice):
    values = [int(seg) for seg in split_choice.value.split("_")]

    # Only validation splits have three values
    have_validataion_split = len(values) == 3

    train_pct = values[0]
    test_pct = values[1]
    val_pct = values[2] if have_validataion_split else 0

    # 80/20 or 60/20/20 can work with 5 folds, otherwise need 10
    n_folds = 10 if 10 in values else 5

    n_train_folds = int((train_pct / 100) * n_folds)
    n_test_folds = int((test_pct / 100) * n_folds)
    n_validation_folds = int((val_pct / 100) * n_folds)

    folds_ids = (["train"] * n_train_folds) + (["test"] * n_test_folds) + (["validate"] * n_validation_folds)
    random.shuffle(folds_ids)
    return folds_ids, n_folds, have_validataion_split


###############################################################################
# ! Commands
###############################################################################
@click.group("splits")
def splits():
    pass


@splits.command("train-test")
@click.option("--split_type", default="80_20", type=click.Choice(SPLIT_CHOICES))
@click.option("--dataset_dir", default=".")
@click.option("--identity_col_name", default="filename")
@click.option("--len_col_name")
@click.option("--random_seed", type=int)
@click.option("--shuffle_segments", default=True)
def train_test_splits(split_type: str,
                      dataset_dir: str,
                      identity_col_name: str,
                      len_col_name: Optional[str],
                      random_seed: Optional[int],
                      shuffle_segments: bool,
                      ):
    split_choice = str_to_enum(split_type, SplitChoice)

    dataset = SeraphDataset(dataset_dir)
    fieldnames, metadata = dataset.get_metadata()

    SPLIT_COL_NAME = "split"

    if SPLIT_COL_NAME not in fieldnames:
        fieldnames.append(SPLIT_COL_NAME)
        splits_are_new = True
    else:
        splits_are_new = False

    if random_seed is not None:
        random.seed(random_seed)

    preproc = _preprocess_split_data(metadata, len_col_name, identity_col_name, shuffle_segments)
    ttv_params, n_folds, have_validation_split = _make_ttv_split_params(split_choice)

    folded_metadata = []
    for cls_records in tqdm(preproc.values(), "Creating splits"):
        folds, _ = _fold_class(cls_records, num_folds=n_folds, add_fold_id_to_clips=False)
        for fold_id, fold in enumerate(folds):
            for split_entry in fold:
                for clip in split_entry.clips:
                    clip[SPLIT_COL_NAME] = ttv_params[fold_id]
                    folded_metadata += clip

    # Save everything
    change = ChangeRecord(
        bump_type=VersionBumpType.MINOR if splits_are_new else VersionBumpType.MAJOR,
        change_type=ChangeType.ADD if splits_are_new else ChangeType.CHANGE,
        message=f"Split test/train{'/validation' if have_validation_split else ''} in proportion {split_choice.value.replace('_', '/')}"
    )
    dataset.set_metadata_headers(fieldnames, change_record=change).set_metadata_records(metadata).save()


@splits.command("fold")
@click.option("--n_folds", default=10)
@click.option("--dataset_dir", default=".")
@click.option("--identity_col_name", default="filename")
@click.option("--len_col_name")
@click.option("--random_seed", type=int)
@click.option("--shuffle_segments", default=True)
@click.option("--shuffle_folds", default=True)
def fold_splits(n_folds: int,
                dataset_dir: str,
                identity_col_name: str,
                len_col_name: Optional[str],
                random_seed: Optional[int],
                shuffle_segments: bool,
                shuffle_folds: bool,
                ):
    if n_folds < 2 or n_folds > 100:
        raise ValueError(f"Number of folds must be in range 2-100 but is {n_folds}")

    dataset = SeraphDataset(dataset_dir)
    fieldnames, metadata = dataset.get_metadata()

    FOLD_COL_NAME = "fold"

    if FOLD_COL_NAME not in fieldnames:
        fieldnames.append(FOLD_COL_NAME)
        folds_are_new = True
    else:
        folds_are_new = False

    if random_seed is not None:
        random.seed(random_seed)

    preproc = _preprocess_split_data(metadata, len_col_name, identity_col_name, shuffle_segments)

    folded_metadata = []
    for cls_records in tqdm(preproc.values(), "Folding classes"):
        folds, _ = _fold_class(cls_records, num_folds=n_folds, shuffle_folds=shuffle_folds)
        for fold in folds:
            for split_entry in fold:
                folded_metadata += split_entry.clips

    # Save everything
    change = ChangeRecord(
        bump_type=VersionBumpType.MINOR if folds_are_new else VersionBumpType.MAJOR,
        change_type=ChangeType.ADD if folds_are_new else ChangeType.CHANGE,
        message=f"{'Added' if folds_are_new else 'Updated'} {n_folds}-validation with per-class DRR assignment"
    )
    dataset.set_metadata_headers(fieldnames, change_record=change).set_metadata_records(metadata).save()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    splits()
