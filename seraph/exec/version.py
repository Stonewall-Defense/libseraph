###############################################################################
# Global Imports
###############################################################################
import io
import os
import re
from typing import Optional

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print

###############################################################################
# Local Imports
###############################################################################
from ..lib import SeraphDataset, VersionBumpType, ChangeType, ChangeRecord, today


###############################################################################
# Constants
###############################################################################
CHANGELOG_FILENAME = "CHANGELOG.md"

VERSION_PATTERN = re.compile(r'^v?(?P<major>\d+)\.(?P<minor>\d+)\.?(?P<patch>\d+)?')

BREAKING_PPRINT_PREFIX = "[bold]BREAKING[/bold] - "
BREAKING_CHANGELOG_PREFIX = "**Breaking:** "


###############################################################################
# Helpers
###############################################################################
def _check_highest_version_bump(changes: list[ChangeRecord]) -> VersionBumpType:
    ret = VersionBumpType.N_A

    for c in changes:
        if c.bump_type == VersionBumpType.MAJOR:
            ret = VersionBumpType.MAJOR
        elif c.bump_type == VersionBumpType.MINOR and ret != VersionBumpType.MAJOR:
            ret = VersionBumpType.MINOR
        elif ret in [VersionBumpType.PATCH, VersionBumpType.N_A]:
            ret = VersionBumpType.PATCH

    return ret


def _determine_next_version(current_version: str,
                            bump_type: VersionBumpType,
                            initial_release: bool,
                            ) -> str:
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

    if initial_release and segs[0] == 0:
        segs = [1, 0, 0]
    elif initial_release:
        raise ValueError(f"Version {current_version} cannot be bumped to an initial release")
    else:
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


def _bump_type_to_color(bump_type: VersionBumpType):
    if bump_type == VersionBumpType.MAJOR:
        return "red"
    elif bump_type == VersionBumpType.MINOR:
        return "blue"
    else:
        return "green"


def _pprint_change_list(changes: list[ChangeRecord]):
    changes_add = [c for c in changes if c.change_type == ChangeType.ADD]
    if len(changes_add):
        print("\n[bold green]Added[/bold green]")
        for change in changes_add:
            prefix = BREAKING_PPRINT_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            print(f"\t- {prefix}{change.message}")

    changes_change = [c for c in changes if c.change_type == ChangeType.CHANGE]
    if len(changes_change):
        print("\n[bold blue]Changed[/bold blue]")
        for change in changes_change:
            prefix = BREAKING_PPRINT_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            print(f"\t- {prefix}{change.message}")

    changes_remove = [c for c in changes if c.change_type == ChangeType.REMOVE]
    if len(changes_remove):
        print("\n[bold strike red]Removed[/bold strike red]")
        for change in changes_remove:
            prefix = BREAKING_PPRINT_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            print(f"\t- {prefix}{change.message}")


def _write_initial_changelog(fq_changelog_path: str):
    with open(fq_changelog_path, "w") as outfile:
        outfile.write("# Changelog\n\n")


def _format_release(next_version: str,
                    change_list: list[ChangeRecord],
                    notice: Optional[str],
                    ):
    ret = io.StringIO()

    ret.write(f"## {next_version} - {today()}\n")

    if notice:
        ret.write(f"\n_{notice}_\n")

    changes_add = [c for c in change_list if c.change_type == ChangeType.ADD]
    if len(changes_add):
        ret.write("\n### Added\n\n")
        for change in changes_add:
            prefix = BREAKING_CHANGELOG_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            ret.write(f"- {prefix}{change.message}\n")

    changes_change = [c for c in change_list if c.change_type == ChangeType.CHANGE]
    if len(changes_change):
        ret.write("\n### Changed\n\n")
        for change in changes_change:
            prefix = BREAKING_CHANGELOG_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            ret.write(f"- {prefix}{change.message}\n")

    changes_remove = [c for c in change_list if c.change_type == ChangeType.REMOVE]
    if len(changes_remove):
        ret.write("\n### Removed\n\n")
        for change in changes_remove:
            prefix = BREAKING_CHANGELOG_PREFIX if change.bump_type == VersionBumpType.MAJOR else ""
            ret.write(f"- {prefix}{change.message}\n")

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
    dataset = SeraphDataset(dataset_dir)
    history = dataset.get_history()

    current_version = dataset.get_seraph_metadata().version
    _, changes = history.load_changes(current_version)

    if not changes:
        print("[yellow]No changes recorded since last version bump[/yellow]")
        return

    bump_type = _check_highest_version_bump(changes)
    next_version = _determine_next_version(current_version, bump_type, False)

    version_color = _bump_type_to_color(bump_type)
    print(f"[bold][white]{current_version} --> [/white][{version_color}]v{next_version}[/{version_color}][white] - {today()}[/white][/bold]")

    _pprint_change_list(changes)


@version.command("list")
@click.option("--dataset_dir", default=".")
@click.option("--versions", multiple=True, help="The versions to show, if any")
def version_list(dataset_dir: str, versions: tuple[str]):
    dataset = SeraphDataset(dataset_dir)
    history = dataset.get_history()
    seraph = dataset.get_seraph_metadata()

    versions_to_pull = list(versions) if versions else None
    records = history.load_change_list(versions_to_pull)

    print(f"[bold][white]Version history for dataset {seraph.name} as of {today()}[/white][/bold]\n")

    for record in records:
        prov_str = "[green]WAS[/green]" if record.prov_was_submitted else "[red]NOT[/red]"
        prefix = "v" if record.version[0] != "v" else ""
        print(f"\n[purple]Changes recorded for {prefix}{record.version} ({record.datetime})[/purple][white](PROVENANCE {prov_str} SUBMITTED)[/white]")
        if not record.changes:
            print("\n[yellow]No changes recorded for this version[/yellow]")
            continue

        _pprint_change_list(changes=record.changes)


@version.command("bump")
@click.option("--dataset_dir", default=".")
@click.option("--notice")
@click.option("--initial_release", is_flag=True, help="Bump directly to version 1.0.0 iff major version is 0")
@click.option("--dry_run", is_flag=True)
def version_bump(dataset_dir: str, notice: Optional[str], initial_release: bool, dry_run: bool):
    # Version
    dataset = SeraphDataset(dataset_dir)
    history = dataset.get_history()
    seraph = dataset.get_seraph_metadata()

    current_version = seraph.version
    _, changes = history.load_changes(current_version)

    if not changes:
        print("[yellow]No changes recorded since last version bump[/yellow]")
        return

    bump_type = _check_highest_version_bump(changes)
    next_version = _determine_next_version(current_version, bump_type, initial_release)

    if dry_run:
        version_color = _bump_type_to_color(bump_type)
        print(f"[bold][white]{current_version} --> [/white][{version_color}]v{next_version}[/{version_color}][white] - {today()}[/white][/bold]")
        return

    seraph.version = next_version
    dataset.set_seraph_metadata(seraph)
    dataset.save()

    # Changelog
    fq_changelog_path = os.path.join(dataset_dir, CHANGELOG_FILENAME)
    if not os.path.isfile(fq_changelog_path):
        _write_initial_changelog(fq_changelog_path)

    notice = notice or ("INITIAL RELEASE TO SEMVER v1.0.0" if initial_release else None)

    release = _format_release(next_version, changes, notice)
    _update_changelog(release, fq_changelog_path)

    history.update_version(next_version)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    version()
