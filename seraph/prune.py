###############################################################################
# Global Imports
###############################################################################
import os

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print

###############################################################################
# Local Imports
###############################################################################
from .dataset import SeraphDataset
from .provenance import ProvenanceActivityType, mark_provenance
from .version import mark_version_note, VersionBumpType, ChangeType


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
        metadata_records = [r for idx, r in enumerate(metadata_records) if idx not in idx_to_remove]
        dataset.set_metadata_records(metadata_records)
        dataset.save()

        # Data governance
        gov_str = f"Pruned {len(idx_to_remove)} records without corresponding files"

        if dataset.track_provenance():
            mark_provenance(ProvenanceActivityType.MODIFIED, gov_str, dataset_dir)

        if dataset.track_version():
            mark_version_note(VersionBumpType.PATCH, ChangeType.REMOVE, gov_str)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    prune()