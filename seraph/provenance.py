###############################################################################
# Global Imports
###############################################################################
from enum import Enum
import os
import pathlib
import re
import shutil
import sys
from typing import Any


###############################################################################
# 3PP Imports
###############################################################################
import click
import requests


###############################################################################
# Local Imports
###############################################################################
from .common import SERAPH_INTERNAL_DIR, str_to_enum
from .dataset import SeraphDataset, SeraphMetadata


###############################################################################
# Enums
###############################################################################
class ProvenanceActivityType(Enum):
    USED = "used"
    MODIFIED = "modified"


###############################################################################
# Constants
###############################################################################
PROV_FILENAME = "provenance.lst"

PROV_RECORD_PATTERN = re.compile(r'^(?P<key>[A-Z]+): (?P<value>.+)$')


###############################################################################
# Helpers
###############################################################################
def _has_provenance_data(dataset_dir=".") -> bool:
    fq_prov_file = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR, PROV_FILENAME)
    return os.path.isfile(fq_prov_file)


def _make_prov_id(seraph: SeraphMetadata):
    return f"{seraph.uri}:{seraph.version}"


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

    response = requests.put(target_url, json=data)
    response.raise_for_status()


def _load_prov(dataset_dir="."):
    fq_prov_file = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR, PROV_FILENAME)

    ret: dict[ProvenanceActivityType, list[str]] = {}
    with open(fq_prov_file, "r") as infile:
        for line in infile:
            matches = re.match(PROV_RECORD_PATTERN, line)
            if not matches:
                raise ValueError(line)

            activity = str_to_enum(matches.group("key").lower(), ProvenanceActivityType)
            ret.setdefault(activity, [])
            ret[activity].append(matches.group("value"))
        return ret


def _submit_activity(seraph: SeraphMetadata,
                     activity_label: str,
                     extra_activity_keywords: list[str],
                     prov_url: str,
                     ):
    target_url = prov_url + "/activity"

    provenance_data = _load_prov()
    keywords = provenance_data.get(ProvenanceActivityType.MODIFIED, [])
    used = provenance_data.get(ProvenanceActivityType.USED, [])

    data = {
        "label": activity_label,
        "keywords": keywords + extra_activity_keywords,
        "used": used,
        "generated": _make_prov_id(seraph),
        "associatedWith": [
            seraph.author.uri,  # type: ignore
        ]
    }

    response = requests.put(target_url, json=data)
    response.raise_for_status()
    return response.text


def _clean_up_provenance(dataset_dir="."):
    fq_prov_dir = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR)
    shutil.rmtree(fq_prov_dir)


###############################################################################
# ! Exports
###############################################################################
def mark_provenance(key: ProvenanceActivityType, value: str, dataset_dir="."):
    fq_prov_dir = os.path.join(dataset_dir, SERAPH_INTERNAL_DIR)
    pathlib.Path(fq_prov_dir).mkdir(parents=True, exist_ok=True)

    fq_prov_file = os.path.join(fq_prov_dir, PROV_FILENAME)

    with open(fq_prov_file, "a") as outfile:
        outfile.write(f"{key.name}: {value}\n")


###############################################################################
# ! Commands
###############################################################################
@click.command("prov")
@click.option("--dataset_dir", default=".")
@click.option("--activity_label", required=True)
@click.option("--activity_keywords", multiple=True)
@click.option("--prov_url", default="https://prospero.sift.net:8000")
@click.option("--clean_up_provenance", default=True)
def prov(dataset_dir: str,
         activity_label: str,
         activity_keywords: tuple[str],
         prov_url: str,
         clean_up_provenance: bool,
         ):
    if not _has_provenance_data(dataset_dir):
        print("No provenance data recorded")
        sys.exit(1)

    dataset = SeraphDataset(dataset_dir)
    seraph = dataset.get_seraph_metadata()

    _submit_dataset(seraph, prov_url)
    _submit_activity(seraph, activity_label, list(activity_keywords), prov_url)

    if clean_up_provenance:
        _clean_up_provenance()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    prov()
