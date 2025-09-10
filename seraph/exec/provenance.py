###############################################################################
# Global Imports
###############################################################################
import re
import sys


###############################################################################
# 3PP Imports
###############################################################################
import click
import requests
from rich import print


###############################################################################
# Local Imports
###############################################################################
from ..lib import SeraphDataset, SeraphMetadata, ChangeRecord, ImportRecord, now


###############################################################################
# Constants
###############################################################################
PROV_RECORD_PATTERN = re.compile(r'^(?P<key>[A-Z]+): (?P<value>.+)$')


###############################################################################
# Helpers
###############################################################################
def _make_prov_id(seraph: SeraphMetadata):
    return f"{seraph.uri}:{seraph.version}"


def _preprocess_prov(dataset: SeraphDataset):
    history = dataset.get_history()
    seraph = dataset.get_seraph_metadata()

    prov_used, prov_modified = history.load_current_changes(seraph.version)

    if not prov_used and not prov_modified:
        print("[yellow]No provenance changes recorded since last version bump[/yellow]")
        sys.exit(0)
    else:
        uri_used = [p.uri for p in prov_used]
        prov_modified = [p for p in prov_modified if all([uri not in p.message for uri in uri_used])]

    return seraph, prov_used, prov_modified


def _submit_dataset(seraph: SeraphMetadata, prov_url: str):
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

    # response = requests.put(target_url, json=data)
    # response.raise_for_status()
    print(data)


def _submit_activity(seraph: SeraphMetadata,
                     prov_used: list[ImportRecord],
                     prov_modified: list[ChangeRecord],
                     activity_label: str,
                     extra_activity_keywords: list[str],
                     prov_url: str,
                     ):
    target_url = prov_url + "/activity"

    data = {
        "label": activity_label,
        "keywords": [m.message for m in prov_modified] + extra_activity_keywords,
        "used": [u.uri for u in prov_used],
        "generated": _make_prov_id(seraph),
        "associatedWith": [
            seraph.author.uri,  # type: ignore
        ]
    }

    # response = requests.put(target_url, json=data)
    # response.raise_for_status()
    # return response.text
    print(data)


###############################################################################
# ! Commands
###############################################################################
@click.group("prov")
def prov():
    pass


@prov.command("show")
@click.option("--dataset_dir", default=".")
def show_prov(dataset_dir: str):
    dataset = SeraphDataset(dataset_dir)
    seraph, prov_used, prov_modified = _preprocess_prov(dataset)

    print(f"[bold white]{seraph.name} provenance updates as of {now()}[/bold white]")

    if len(prov_used):
        print("\n[bold green]Used[/bold green]")
        for used in prov_used:
            print(f"\t- {used.uri}")

    if len(prov_modified):
        print("\n[bold blue]Modified[/bold blue]")
        for mod in prov_modified:
            print(f"\t- {mod.message}")


@prov.command("submit")
@click.option("--dataset_dir", default=".")
@click.option("--activity_label", required=True)
@click.option("--activity_keywords", multiple=True)
@click.option("--prov_url", default="https://prospero.sift.net:8000")
def submit_prov(dataset_dir: str,
                activity_label: str,
                activity_keywords: tuple[str],
                prov_url: str,
                ):

    dataset = SeraphDataset(dataset_dir)
    seraph, prov_used, prov_modified = _preprocess_prov(dataset)

    _submit_dataset(seraph, prov_url)
    _submit_activity(seraph, prov_used, prov_modified, activity_label, list(activity_keywords), prov_url)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    prov()
