###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
import re
import sys
from typing import Optional

###############################################################################
# 3PP Imports
###############################################################################
import click
import requests
from rich import print


###############################################################################
# Local Imports
###############################################################################
from ..lib import SeraphDataset, SeraphMetadata, ChangeRecord, ImportRecord, now_str, load_license


###############################################################################
# Classes
###############################################################################
@dataclass
class ProvMeta:
    seraph: SeraphMetadata
    prov_version: str
    prov_used: list[ImportRecord]
    prov_modified: list[ChangeRecord]
    prov_was_submitted: bool


###############################################################################
# Constants
###############################################################################
PROV_RECORD_PATTERN = re.compile(r'^(?P<key>[A-Z]+): (?P<value>.+)$')


###############################################################################
# Helpers
###############################################################################
def _make_prov_id(seraph: SeraphMetadata):
    return f"{seraph.uri}:{seraph.version}"


def _preprocess_prov(dataset: SeraphDataset, version: Optional[str] = None) -> ProvMeta:
    history = dataset.get_history()
    seraph = dataset.get_seraph_metadata()

    version_to_use = version or seraph.version

    prov_used, prov_modified = history.load_changes(version_to_use)

    if not prov_used and not prov_modified:
        print("[yellow]No provenance changes recorded since last version bump[/yellow]")
        sys.exit(0)
    else:
        prov_modified = [p for p in prov_modified if not p.is_import]

    prov_was_submitted = history.check_prov_submission()

    return ProvMeta(
        seraph=seraph,
        prov_version=version_to_use,
        prov_used=prov_used,
        prov_modified=prov_modified,
        prov_was_submitted=prov_was_submitted,
    )


def _submit_dataset(prov: ProvMeta, prov_url: str):
    seraph = prov.seraph

    target_url = prov_url + "/dataset"
    data = {
        "@id": _make_prov_id(seraph),
        "label": [
            seraph.name,
            seraph.version,
        ],
        "keywords": seraph.keywords,
        "associatedWith": [
            seraph.author.uri,  # type: ignore
        ]
    }

    response = requests.put(target_url, json=data)
    response.raise_for_status()


def _submit_activity(prov: ProvMeta,
                     activity_label: str,
                     extra_activity_keywords: list[str],
                     prov_url: str,
                     ):
    target_url = prov_url + "/activity"

    data = {
        "label": activity_label,
        "keywords": [m.message for m in prov.prov_modified] + extra_activity_keywords,
        "used": [u.uri for u in prov.prov_used],
        "generated": _make_prov_id(prov.seraph),
        "associatedWith": [
            prov.seraph.author.uri,  # type: ignore
        ]
    }

    response = requests.put(target_url, json=data)
    response.raise_for_status()
    return response.text


def _submit_license(prov: ProvMeta, prov_url: str):
    uri = _make_prov_id(prov.seraph)
    license = prov.seraph.license

    if not license:
        raise ValueError(f"No license recorded for dataset {uri}")
    full_license = load_license(license)

    target_url = prov_url + "/tag_with"

    data = {
        "in": uri,
        "out": full_license.url if full_license else license
    }

    response = requests.put(target_url, json=data)
    response.raise_for_status()
    return response.text


###############################################################################
# ! Commands
###############################################################################
@click.group("prov", help="[EXPERIMENTAL] Manage provenance with Prospero from SIFT Technologies")
def prov():
    pass


@prov.command("show", help="Show provenance updates per version")
@click.option("--dataset_dir", default=".")
@click.option("--version")
def show_prov(dataset_dir: str, version: Optional[str]):
    dataset = SeraphDataset(dataset_dir)
    prov = _preprocess_prov(dataset, version)

    version = prov.prov_version
    prefix = "" if version.startswith("v") else "v"

    title = f"[bold][white]{prov.seraph.name} provenance updates for {prefix}{version} as of {now_str()}[/white] "
    if prov.prov_was_submitted:
        title += "[green](SUBMITTED)[/green]"
    else:
        title += "[yellow](NOT SUBMITTED)[/yellow]"

    title += "[/bold]"
    print(title)

    if len(prov.prov_used):
        print("\n[bold green]Used[/bold green]")
        for used in prov.prov_used:
            print(f"\t- {used.uri}")

    if len(prov.prov_modified):
        print("\n[bold blue]Modified[/bold blue]")
        for mod in prov.prov_modified:
            print(f"\t- {mod.message}")


@prov.command("submit", help="Submit a dataset or update to Prospero")
@click.option("--dataset_dir", default=".")
@click.option("--activity_label", required=True)
@click.option("--activity_keywords", multiple=True)
@click.option("--prov_url", default="https://prospero.sift.net:8000")
@click.option("--version")
@click.option("--force", is_flag=True)
@click.option("--license", is_flag=True)
def submit_prov(dataset_dir: str,
                activity_label: str,
                activity_keywords: tuple[str],
                prov_url: str,
                version: Optional[str],
                force: bool,
                license: bool,
                ):

    dataset = SeraphDataset(dataset_dir)
    prov = _preprocess_prov(dataset, version)

    if prov.prov_was_submitted:
        if force:
            print(f"[yellow]Provenance was already submitted for v{prov.prov_version}; resubmitting now ...[/yellow]")
        else:
            print(f"[red]Provenance was already submitted for v{prov.prov_version}; retry with `--force` if you're determined to resubmit.[/red]")
            return

    _submit_dataset(prov, prov_url)
    _submit_activity(prov, activity_label, list(activity_keywords), prov_url)

    if license:
        _submit_license(prov, prov_url)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    prov()
