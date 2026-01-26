###############################################################################
# Global Imports
###############################################################################
import os
from typing import Optional

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print

###############################################################################
# Local Imports
###############################################################################
from ..lib import SeraphDataset, VersionBumpType, ChangeType, ChangeRecord


###############################################################################
# Helpers
###############################################################################
def _remove_files(data_dir: str, files_to_keep: set[str], dry_run=False):
    files = os.listdir(data_dir)
    files_removed = 0
    for f in files:
        fq_filename = os.path.join(data_dir, f)
        if f not in files_to_keep:
            if dry_run:
                print(f"[red bold]REMOVING[/red bold] file {fq_filename}")
            else:
                os.unlink(fq_filename)
                files_removed += 1
    return files_removed


###############################################################################
# ! Commands
###############################################################################
@click.group("prune", help="Commands for intelligently removing (meta)data from the dataset")
def prune():
    pass


@prune.command("files", help="Remove all files without a corresponding metadata record")
@click.option("--dataset_dir", default=".")
@click.option("--dry_run", is_flag=True)
def prune_files(dataset_dir: str, dry_run: bool):
    dataset = SeraphDataset(dataset_dir)
    data_dir = dataset.get_data_dir()
    _, metadata_records = dataset.get_metadata()

    files_to_keep = set([record["filename"] for record in metadata_records])
    files_removed = _remove_files(data_dir, files_to_keep, dry_run)

    if files_removed:
        change = ChangeRecord(
            bump_type=VersionBumpType.PATCH,
            change_type=ChangeType.REMOVE,
            message=f"Pruned {files_removed} files without corresponding metadata entries",
        )
        dataset.register_patch_update(change).save()


@prune.command("records", help="Remove all metadata records without a corresponding data file")
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

        change = ChangeRecord(
            bump_type=VersionBumpType.PATCH,
            change_type=ChangeType.REMOVE,
            message=f"Pruned {len(idx_to_remove)} records without corresponding files",
        )
        dataset.set_metadata_records(metadata_records, change_record=change).save()


@prune.command("column", help="Remove a columnar property from every metadata record")
@click.option("--dataset_dir", default=".")
@click.option("--column_name", multiple=True, required=True)
def prune_column(dataset_dir: str, column_name: tuple[str]):
    dataset = SeraphDataset(dataset_dir)
    headers, metadata_records = dataset.get_metadata()

    for col in column_name:
        try:
            headers.remove(col)
        except ValueError:
            print(f"[yellow]Column {col} is not present in the metadata[/yellow]")
            return

    for record in metadata_records:
        for col in column_name:
            del record[col]

    change = ChangeRecord(
        bump_type=VersionBumpType.MAJOR,
        change_type=ChangeType.REMOVE,
        message=f"Dropped column{'s' if len(column_name) > 1 else ''} {column_name[0] if len(column_name) == 1 else ', '.join(column_name)}",
    )
    dataset.set_multiple(metadata_headers=headers, metadata_records=metadata_records, change_records=[change]).save()


@prune.command("rows", help="Remove all metadata records with the provided value in the provided column")
@click.option("--dataset_dir", default=".")
@click.option("--column_name", required=True)
@click.option("--rm_row_val")
@click.option("--remove_empty", is_flag=True)
def prune_rows(dataset_dir: str,
               column_name: str,
               rm_row_val: Optional[str],
               remove_empty: bool,
               ):
    dataset = SeraphDataset(dataset_dir)
    data_dir = dataset.get_data_dir()
    headers, metadata_records = dataset.get_metadata()

    if column_name not in headers:
        print(f"[yellow]Column {column_name} is not present in the metadata[/yellow]")
        return
    elif not rm_row_val and not remove_empty:
        print("[yellow]You must specify either a `rm_row_val` to match, and/or to `remove_empty` [/yellow]")
        return

    idx_to_remove = []

    for idx, record in enumerate(metadata_records):
        row_val = record[column_name]
        if (rm_row_val and row_val == rm_row_val) or (remove_empty and not row_val):
            idx_to_remove.append(idx)

    if len(idx_to_remove):
        new_metadata_records = []
        files_to_keep = set()

        for idx, record in enumerate(metadata_records):
            if idx not in idx_to_remove:
                new_metadata_records.append(record)
                files_to_keep.add(record["filename"])
            else:
                pass

        _remove_files(data_dir, files_to_keep)

        # Save data
        str_1 = f"had a value of {rm_row_val}" if rm_row_val else ""
        str_2 = "was empty" if remove_empty else ""
        link = " or " if (str_1 and str_2) else ""
        gov_str = f"Removed {len(idx_to_remove)} records where {column_name} {str_1}{link}{str_2}"

        change = ChangeRecord(
            bump_type=VersionBumpType.PATCH,
            change_type=ChangeType.REMOVE,
            message=gov_str,
        )
        dataset.set_metadata_records(new_metadata_records, change_record=change).save()


@prune.command("dupes", help="Remove all but the first metadata record with a duplicate value for `identity_column`")
@click.option("--dataset_dir", default=".")
@click.option("--identity_column", required=True)
def prune_dupes(dataset_dir: str, identity_column: str):
    dataset = SeraphDataset(dataset_dir)
    data_dir = dataset.get_data_dir()
    _, metadata_records = dataset.get_metadata()

    ids_seen = set()
    new_metadata_records = []
    files_to_keep = set()

    records_removed = 0

    for record in metadata_records:
        id = record[identity_column]
        filename = record["filename"]

        if id not in ids_seen:
            ids_seen.add(id)
            new_metadata_records.append(record)
            files_to_keep.add(filename)
        else:
            records_removed += 1

    _ = _remove_files(data_dir, files_to_keep, False)

    if records_removed:
        change = ChangeRecord(
            bump_type=VersionBumpType.PATCH,
            change_type=ChangeType.REMOVE,
            message=f"Pruned {records_removed} duplicate metadata entries",
        )
        dataset.set_metadata_records(new_metadata_records, change_record=change).save()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    prune()
