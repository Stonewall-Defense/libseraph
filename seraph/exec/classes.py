###############################################################################
# Global Imports
###############################################################################
from fractions import Fraction
from itertools import zip_longest
import os
import re
from typing import Optional

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print
from rich.table import Column, Table

###############################################################################
# Local Imports
###############################################################################
from ..lib import read_csv, write_csv, write_json, get_input, get_metadata_filename, SeraphDataset, VersionBumpType, ChangeType, ChangeRecord, CLASSFILE_NAME


###############################################################################
# Helpers
###############################################################################
def _ratio_color(siz: int, max_siz: int):
    ratio = siz / max_siz

    if ratio > 1 / 2:
        return "green"
    elif ratio > 1 / 4:
        return "yellow"
    else:
        return "red"


def _pprint_ratio(val: float):
    frac = Fraction(val)
    denom = round(frac.denominator / (frac.numerator or 1))
    return f"1/{denom}"


def _pprint_class_balance(class_list: list[str], mapped_class_totals: dict[str, int]):
    max_siz = max(mapped_class_totals.values())
    min_siz = min(mapped_class_totals.values())

    max_bal = min_siz / max_siz
    max_bal_color = _ratio_color(min_siz, max_siz)

    table = Table(
        "Class Name",
        Column("Data Size", justify="right"),
        Column("Class Ratio", justify="right"),
        title=f"Class Balances (overall [{max_bal_color}]{_pprint_ratio(max_bal)}[/{max_bal_color}])"
    )

    for cls in class_list:
        siz = mapped_class_totals[cls]
        bal = siz / max_siz
        bal_color = _ratio_color(siz, max_siz)
        table.add_row(cls, str(int(siz)), f"[{bal_color}]{_pprint_ratio(bal)}[/{bal_color}]")
    print(table)


def _print_class_match_list(matches: list[str], survivors: list[str], target: str, pattern: str):
    table = Table(
        Column("Survivors", justify="left"),
        Column("Matches", justify="left"),
        title=f"Effects of Merging Classes Into `{target}` via match {pattern}"
    )

    for s, m in zip_longest(survivors, matches):
        table.add_row(f"[green]{s}[/green]" if s else "", f"[red]{m}[/red]")
    print(table)


###############################################################################
# ! Commands
###############################################################################
@click.group("classes")
def classes():
    pass


@classes.command("switch")
@click.option("--dataset_dir", default=".")
@click.option("--new_class_col", required=True)
@click.option("--new_name_for_current_class_col", required=True)
@click.option("--keep_class_col_as_field", default=True)
@click.option("--sort_classes", default=True)
def switch_classes(dataset_dir: str,
                   new_class_col: str,
                   new_name_for_current_class_col: str,
                   keep_class_col_as_field: bool,
                   sort_classes: bool,
                   ):
    dataset = SeraphDataset(dataset_dir)
    fields, metadata = dataset.get_metadata()

    if not len(metadata):
        raise NotImplementedError("For now, there must be metadata in the file to execute this operation")
    elif new_class_col not in metadata[0].keys():
        raise ValueError(f"Key {new_class_col} is not a field in the metadata")
    else:
        fields.append(new_name_for_current_class_col)

    new_classes = list(set([entry[new_class_col] for entry in metadata]))
    if sort_classes:
        new_classes.sort()

    for entry in metadata:
        new_class_name = entry[new_class_col]
        new_class_id = new_classes.index(new_class_name)

        entry[new_name_for_current_class_col] = entry["class_name"]
        entry["class_id"] = str(new_class_id)
        entry["class_name"] = new_class_name

        if not keep_class_col_as_field:
            del entry[new_class_col]

    # Save everything
    changes = [
        ChangeRecord(
            bump_type=VersionBumpType.MAJOR,
            change_type=ChangeType.ADD,
            message=f"Changed class column to {new_class_col}"
        ),
        ChangeRecord(
            bump_type=VersionBumpType.MAJOR,
            change_type=ChangeType.CHANGE,
            message=f"Renamed previous class column to {new_name_for_current_class_col}"
        ),
    ]
    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=new_classes,
                         change_records=changes,
                         )
    dataset.save()


@classes.command("rename")
@click.option("--dataset_dir", default=".")
@click.option("--new_class_name", required=True)
@click.option("--old_class_name", required=True)
@click.option("--sort_classes", default=True)
def rename_classes(dataset_dir: str,
                   new_class_name: str,
                   old_class_name: str,
                   sort_classes: bool,
                   ):
    dataset = SeraphDataset(dataset_dir)
    fields, metadata = dataset.get_metadata()
    class_list = dataset.get_classes()

    if not len(metadata):
        raise NotImplementedError("For now, there must be metadata in the file to execute this operation")
    elif new_class_name in class_list:
        raise ValueError(f"Target class {new_class_name} is already a class in this dataset; use merge instead")
    elif old_class_name not in class_list:
        raise ValueError(f"Class {old_class_name} is not a current class")

    old_class_idx = class_list.index(old_class_name)
    class_list[old_class_idx] = new_class_name
    if sort_classes:
        class_list.sort()

    for entry in metadata:
        old_entry_class_name = entry["class_name"]
        entry_class_name = new_class_name if old_entry_class_name == old_class_name else old_entry_class_name
        entry_class_id = class_list.index(entry_class_name)

        entry["class_id"] = str(entry_class_id)
        entry["class_name"] = entry_class_name

    # Save everything
    change = ChangeRecord(
        bump_type=VersionBumpType.MAJOR,
        change_type=ChangeType.CHANGE,
        message=f"Renamed class {old_class_name} to {new_class_name}"
    )
    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=class_list,
                         change_records=[change],
                         )
    dataset.save()


@classes.command("merge")
@click.option("--dataset_dir", default=".")
@click.option("--target_class_name", required=True)
@click.option("--classes_to_merge", required=True, multiple=True)
@click.option("--sort_classes", default=True)
def merge_classes(dataset_dir: str,
                  target_class_name: str,
                  classes_to_merge: tuple[str],
                  sort_classes: bool,
                  ):
    # Setup
    dataset = SeraphDataset(dataset_dir)
    fields, metadata = dataset.get_metadata()
    class_list = dataset.get_classes()

    # Sanity checks
    if not len(metadata):
        raise NotImplementedError("For now, there must be metadata in the file to execute this operation")
    elif not len(classes_to_merge):
        raise ValueError("Must specify at least one class to merge")

    # Generate new metadata
    new_class_list = [c for c in class_list if c not in classes_to_merge]
    if target_class_name not in new_class_list:
        new_class_list.append(target_class_name)

    if sort_classes:
        new_class_list.sort()

    # Process old metadata
    for entry in metadata:
        old_entry_class_name = entry["class_name"]
        entry_class_name = target_class_name if old_entry_class_name in classes_to_merge else old_entry_class_name
        entry_class_id = new_class_list.index(entry_class_name)

        entry["class_id"] = str(entry_class_id)
        entry["class_name"] = entry_class_name

    # Save everything
    if len(classes_to_merge) > 1:
        prefix = "es " + ", ".join(classes_to_merge)
    else:
        prefix = f" {classes_to_merge[0]}"
    gov_str = f"Merged class{prefix} into {target_class_name}"

    change = ChangeRecord(
        bump_type=VersionBumpType.MAJOR,
        change_type=ChangeType.CHANGE,
        message=gov_str
    )
    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=new_class_list,
                         change_records=[change],
                         )
    dataset.save()


@classes.command("regex-merge")
@click.option("--dataset_dir", default=".")
@click.option("--target_class_name", required=True)
@click.option("--sort_classes", default=True)
@click.option("--dry_run", is_flag=True)
def merge_classes_regex(dataset_dir: str,
                        target_class_name: str,
                        sort_classes: bool,
                        dry_run: bool,
                        ):
    # Setup
    dataset = SeraphDataset(dataset_dir)
    fields, metadata = dataset.get_metadata()
    class_list = dataset.get_classes()

    class_merge_regex = get_input("Class merge regex: ")

    # Sanity checks
    if not len(metadata):
        raise NotImplementedError("For now, there must be metadata in the file to execute this operation")
    elif not len(class_merge_regex):
        raise ValueError("Must specify a regex to capture classes")

    pattern = re.compile(class_merge_regex)

    if dry_run:
        matches = sorted([c for c in class_list if re.match(pattern, c)])
        survivors = sorted([c for c in class_list if not re.match(pattern, c)])
        _print_class_match_list(matches, survivors, target_class_name, class_merge_regex)
        return

    # Generate new metadata
    new_class_list = [c for c in class_list if not re.match(pattern, c)]

    if target_class_name not in new_class_list:
        new_class_list.append(target_class_name)

    if sort_classes:
        new_class_list.sort()

    # Process old metadata
    for entry in metadata:
        old_entry_class_name = entry["class_name"]
        entry_class_name = target_class_name if re.match(pattern, old_entry_class_name) else old_entry_class_name
        entry_class_id = new_class_list.index(entry_class_name)

        entry["class_id"] = str(entry_class_id)
        entry["class_name"] = entry_class_name

    # Save everything
    change = ChangeRecord(
        bump_type=VersionBumpType.MAJOR,
        change_type=ChangeType.CHANGE,
        message=f"Merged classes into {target_class_name} by regex match",
    )
    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=new_class_list,
                         change_records=[change]
                         )
    dataset.save()


@classes.command("check-balance")
@click.option("--dataset_dir", default=".")
@click.option("--len_col_name")
def classes_check_balance(dataset_dir: str, len_col_name: Optional[str]):
    # Setup
    dataset = SeraphDataset(dataset_dir)
    _, metadata = dataset.get_metadata()
    class_list = dataset.get_classes()

    mapped_class_totals = {}
    for cls in class_list:
        mapped_class_totals[cls] = 0

    for record in metadata:
        cls = record["class_name"]
        siz = record[len_col_name] if len_col_name else 1
        siz = siz or 1
        mapped_class_totals[cls] += float(siz)

    _pprint_class_balance(class_list, mapped_class_totals)


@classes.command("compose")
@click.option("--target_dir", default=".")
@click.option("--compose_col", multiple=True)
@click.option("--separator_char", default=" ")
def classes_compose(target_dir: str, compose_col: tuple[str], separator_char: str):
    fq_class_file = os.path.join(target_dir, CLASSFILE_NAME)
    classes_tmp = set()

    metadata_filename = get_metadata_filename(target_dir)
    fq_metadata_file = os.path.join(target_dir, metadata_filename)
    headers, metadata = read_csv(fq_metadata_file)

    if not all([c in headers for c in compose_col]):
        raise ValueError("At least one compose_col is not present in the metadata")

    for record in metadata:
        class_name = separator_char.join([record[c] for c in compose_col])
        classes_tmp.add(class_name)
        record["class_name"] = class_name

    class_list = sorted(list(classes_tmp))
    write_json(fq_class_file, class_list)

    headers.insert(0, "class_id")
    headers.insert(1, "class_name")
    for r in metadata:
        r["class_id"] = str(class_list.index(r["class_name"]))

    write_csv(fq_metadata_file, headers, metadata)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    classes()
