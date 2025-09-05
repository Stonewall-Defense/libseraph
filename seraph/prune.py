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
# ! Commands
###############################################################################
@click.group("prune")
def prune():
    pass

@prune.command("files")
@click.option("--dataset_dir", default=".")
@click.option("--dry_run", is_flag=True)
def prune_files(dataset_dir: str, dry_run: bool):
    dataset = SeraphDataset(dataset_dir)
    data_dir = dataset.get_data_dir()
    _, metadata_records = dataset.get_metadata()
    files_to_keep = set([record["filename"] for record in metadata_records])

    files = os.listdir(data_dir)
    for f in files:
        fq_filename = os.path.join(data_dir, f)
        if f not in files_to_keep:
            if dry_run:
                print(f"[red bold]REMOVING[/red bold] file {fq_filename}")
            else:
                os.unlink(fq_filename)


@prune.command("records")
@click.option("--dataset_dir", default=".")
@click.option("--dry_run", is_flag=True)
def prune_records(dataset_dir: str, dry_run: bool):
    dataset = SeraphDataset(dataset_dir)
    data_dir = dataset.get_data_dir()
    _, metadata_records = dataset.get_metadata()

    files = set(os.listdir(data_dir))
    idx_to_remove = []

    for idx, record in enumerate(metadata_records):
        recorded_filename = record["filename"]
        if recorded_filename not in files:
            if dry_run:
                print(f"[red bold]REMOVING[/red bold] record {idx} - {recorded_filename}")
            else:
                idx_to_remove.append(idx)

    if len(idx_to_remove):
        for idx in idx_to_remove:
            del metadata_records[idx]
        dataset.set_metadata_records(metadata_records)
        dataset.save()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    prune()