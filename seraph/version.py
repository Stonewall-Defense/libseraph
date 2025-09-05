###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import io
import os
import pathlib
import re
import sys
from typing import Optional

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print

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
VERSION_PATTERN = re.compile(r'^v?(?P<major>\d+)\.(?P<minor>\d+)\.?(?P<patch>\d+)?')

BREAKING_PPRINT_PREFIX = "[bold]BREAKING[/bold] - "
BREAKING_CHANGELOG_PREFIX = "**Breaking:** "


###############################################################################
# Helpers
###############################################################################
def _has_version_data(dataset_dir=".") -> bool:
    fq_version_file = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR, VERSION_FILENAME)
    return os.path.isfile(fq_version_file)


def _check_highest_version_bump(prev: VersionBumpType, curr: VersionBumpType) -> VersionBumpType:
    if curr == VersionBumpType.MAJOR:
        return VersionBumpType.MAJOR
    elif curr == VersionBumpType.MINOR:
        if prev == VersionBumpType.MAJOR:
            return VersionBumpType.MAJOR
        else:
            return VersionBumpType.MINOR
    else:
        return VersionBumpType.PATCH


def _load_change_list(dataset_dir="."):
    fq_version_file = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR, VERSION_FILENAME)

    change_list: dict[ChangeType, list[ChangeRecord]] = {}
    highest_version_bump_type = VersionBumpType.N_A
    with open(fq_version_file, "r") as infile:
        for line in infile:
            matches = re.match(CHANGE_RECORD_PATTERN, line)
            if not matches:
                raise ValueError(line)

            bump_type = str_to_enum(matches.group("bump_type").lower(), VersionBumpType)
            change_type = str_to_enum(matches.group("change_type").lower(), ChangeType)
            message = matches.group("message")

            change_list.setdefault(change_type, [])

            change_list[change_type].append(ChangeRecord(bump_type=bump_type, change_type=change_type, message=message))
            highest_version_bump_type = _check_highest_version_bump(highest_version_bump_type, bump_type)

        return change_list, highest_version_bump_type


def _determine_next_version(current_version: str, bump_type: VersionBumpType) -> str:
    matches = re.match(VERSION_PATTERN, current_version)
    if not matches:
        raise ValueError(f"Invalid version number: {current_version}")
    major = int(matches.group("major"))
    minor = int(matches.group("minor"))

    try:
        patch = int(matches.group("patch"))
    except ValueError:
        patch = 0

    segs = [major, minor, patch]

    if bump_type == VersionBumpType.MAJOR:
        if major == 0:
            segs = [0, segs[1] + 1, 0]
        else:
            segs = [segs[0] + 1, 0, 0]
    elif bump_type == VersionBumpType.MINOR:
        segs = [segs[0], segs[1] + 1, 0]
    elif bump_type == VersionBumpType.MINOR:
        segs[2] += 1
    else:
        pass

    return ".".join([str(seg) for seg in segs])


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _bump_type_to_color(bump_type: VersionBumpType):
    if bump_type == VersionBumpType.MAJOR:
        return "red"
    elif bump_type == VersionBumpType.MINOR:
        return "blue"
    else:
        return "green"


def _clean_up_versioning(dataset_dir="."):
    fq_ver_file = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR, VERSION_FILENAME)
    os.unlink(fq_ver_file)


def _write_initial_changelog(fq_changelog_path: str):
    with open(fq_changelog_path, "w") as outfile:
        outfile.write("# Changelog\n\n")


def _format_release(next_version: str,
                    change_list: dict[ChangeType, list[ChangeRecord]],
                    notice: Optional[str],
                    ):
    ret = io.StringIO()

    ret.write(f"## {next_version} - {_today()}")

    if notice:
        ret.write(f"_{notice}_")

    changes_add = change_list.get(ChangeType.ADD, [])
    if len(changes_add):
        ret.write("\n\n### Added\n")
        for change in changes_add:
            prefix = BREAKING_CHANGELOG_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            ret.write(f"  - {prefix}{change.message}\n")

    changes_change = change_list.get(ChangeType.CHANGE, [])
    if len(changes_change):
        ret.write("\n\n### Changed\n")
        for change in changes_change:
            prefix = BREAKING_CHANGELOG_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            ret.write(f"  - {prefix}{change.message}\n")

    changes_remove = change_list.get(ChangeType.REMOVE, [])
    if len(changes_remove):
        ret.write("\n\n### Removed\n")
        for change in changes_remove:
            prefix = BREAKING_CHANGELOG_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            ret.write(f"  - {prefix}{change.message}\n")

    ret.write("\n")

    return ret.getvalue()


def _read_chaneglog(fq_changelog_path: str):
    with open(fq_changelog_path, "r") as infile:
        return infile.readlines()


def _update_changelog(release: str, fq_changelog_path: str):
    lines = _read_chaneglog(fq_changelog_path)

    output = io.StringIO()

    line_insert_idx = 0
    written = False

    for line in lines:
        if line.startswith("##"):
            output.write(release)
            written = True
            break
        else:
            output.write(line)
            line_insert_idx += 1

    if not written:
        output.write(release)

    for line in lines[line_insert_idx:]:
        output.write(line)

    with open(fq_changelog_path, "w") as outfile:
        outfile.write(output.getvalue())


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
    """
        References:
            https://common-changelog.org/
            https://github.com/dslp/dslp/blob/main/semantic-versioning.md
    """
    pass


@version.command("show")
@click.option("--dataset_dir", default=".")
def version_show(dataset_dir: str):
    if not _has_version_data(dataset_dir):
        print("No version data recorded")
        sys.exit(1)

    dataset = SeraphDataset(dataset_dir)

    current_version = dataset.get_seraph_metadata().version or "0.0.0"
    changes, bump_type = _load_change_list(dataset_dir)

    next_version = _determine_next_version(current_version, bump_type)

    today = _today()

    version_color = _bump_type_to_color(bump_type)
    print(f"[bold][white]{current_version} --> [/white][{version_color}]v{next_version}[/{version_color}][white] - {today}[/white][/bold]")

    changes_add = changes.get(ChangeType.ADD, [])
    if len(changes_add):
        print("\n[bold green]Added[/bold green]")
        for change in changes_add:
            prefix = BREAKING_PPRINT_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            print(f"\t- {prefix}{change.message}")

    changes_change = changes.get(ChangeType.CHANGE, [])
    if len(changes_change):
        print("\n[bold blue]Changed[/bold blue]")
        for change in changes_change:
            prefix = BREAKING_PPRINT_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            print(f"\t- {prefix}{change.message}")

    changes_remove = changes.get(ChangeType.REMOVE, [])
    if len(changes_remove):
        print("\n[bold strike red]Removed[/bold strike red]")
        for change in changes_remove:
            prefix = BREAKING_PPRINT_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            print(f"\t- {prefix}{change.message}")


@version.command("bump")
@click.option("--dataset_dir", default=".")
@click.option("--notice")
@click.option("--clean_up_versioning", default=False)   # TODO: FIXME
def version_bump(dataset_dir: str, notice: Optional[str], clean_up_versioning: bool):
    if not _has_version_data(dataset_dir):
        print("No version data recorded")
        sys.exit(1)

    # Version
    dataset = SeraphDataset(dataset_dir)
    seraph = dataset.get_seraph_metadata()

    current_version = seraph.version or "0.0.0"
    changes, bump_type = _load_change_list(dataset_dir)

    next_version = _determine_next_version(current_version, bump_type)

    seraph.version = next_version
    # dataset.set_seraph_metadata(seraph)
    # dataset.save()

    # Changelog
    fq_changelog_path = os.path.join(dataset_dir, CHANGELOG_FILENAME)
    if not os.path.isfile(fq_changelog_path):
        _write_initial_changelog(fq_changelog_path)

    release = _format_release(next_version, changes, notice)
    _update_changelog(release, fq_changelog_path)

    # Cleanup
    if clean_up_versioning:
        _clean_up_versioning(dataset_dir)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    version()
