###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import os
import pathlib
import re

###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from .common import SERAPH_INTERNAL_DIR, str_to_enum
from .dataset import SeraphDataset


###############################################################################
# Enums
###############################################################################
class VersionBumpType(Enum):
    N_A = "n/a"     # Not used
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


class ChangeType(Enum):
    ADD = "add"
    CHANGE = "change"
    REMOVE = "remove"


###############################################################################
# Classes
###############################################################################
@dataclass
class ChangeRecord:
    bump_type: VersionBumpType
    change_type: ChangeType
    message: str


###############################################################################
# Constants
###############################################################################
VERSION_FILENAME = "changes.ver"
CHANGELOG_FILENAME = "CHANGELOG.md"

CHANGE_RECORD_PATTERN = re.compile(r'^(?P<bump_type>[A-Z]+) (?P<change_type>[A-Z]+) (?P<message>.+)$')


###############################################################################
# Helpers
###############################################################################
def _check_highest_version_bump(prev: VersionBumpType, curr: VersionBumpType) -> VersionBumpType:
    if curr == VersionBumpType.MAJOR:
        return VersionBumpType.MAJOR
    elif curr == VersionBumpType.MINOR and prev != VersionBumpType.MAJOR:
        return VersionBumpType.MINOR
    else:
        return VersionBumpType.PATCH


def _load_change_list(dataset_dir="."):
    fq_version_file = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR, VERSION_FILENAME)

    change_list: list[ChangeRecord] = []
    highest_version_bump_type = VersionBumpType.N_A
    with open(fq_version_file, "r") as infile:
        for line in infile:
            matches = re.match(CHANGE_RECORD_PATTERN, line)
            if not matches:
                raise ValueError(line)

            bump_type = str_to_enum(matches.group("bump_type").lower(), VersionBumpType)
            change_type = str_to_enum(matches.group("change_type").lower(), ChangeType)
            message = matches.group("message")

            change_list.append(ChangeRecord(bump_type=bump_type, change_type=change_type, message=message))
            highest_version_bump_type = _check_highest_version_bump(change_list[-1].bump_type, bump_type)

        return change_list, highest_version_bump_type


def _determine_next_version(current_version: str, bump_type: VersionBumpType) -> str:
    segs = [int(seg) for seg in current_version.split(".")]
    if bump_type == VersionBumpType.MAJOR:
        if segs[0] == 0:
            segs = [0, segs[1] + 1, 0]
        else:
            segs = [segs[0] + 1, 0, 0]
    elif bump_type == VersionBumpType.MINOR:
        segs = [segs[0], segs[1] + 1, 0]
    elif bump_type == VersionBumpType.MINOR:
        segs[2] += 1
    else:
        pass

    return ".".join(segs)  # type: ignore


def _now():
    return datetime.now().strftime("%Y-%m-%d")


###############################################################################
# ! Exports
###############################################################################
def mark_version_note(version_bump_type: VersionBumpType, change_type: ChangeType, message: str, dataset_dir="."):
    fq_ver_dir = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR)
    pathlib.Path(fq_ver_dir).mkdir(parents=True, exist_ok=True)

    fq_prov_file = os.path.join(fq_ver_dir, VERSION_FILENAME)

    with open(fq_prov_file, "a") as outfile:
        outfile.write(f"{version_bump_type.name} {change_type.name} {message}\n")


###############################################################################
# ! Commands
###############################################################################
@click.group("version")
def version():
    pass


@version.command("show")
@click.option("--dataset_dir", default=".")
def version_show(dataset_dir: str):
    dataset = SeraphDataset(dataset_dir)

    current_version = dataset.get_seraph_metadata().version or "0.0.0"
    changes, bump_type = _load_change_list(dataset_dir)

    next_version = _determine_next_version(current_version, bump_type)

    now = _now()

    print(f"{current_version} --> {next_version} - {now}")
    for change in changes:
        print(f"{change.bump_type} {change.change_type} {change.message}")


@version.command("bump")
@click.option("--dataset_dir", default=".")
def version_bump(dataset_dir: str):
    pass


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    version()
