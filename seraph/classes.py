###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from .dataset import SeraphDataset
from .provenance import ProvenanceActivityType, mark_provenance


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

    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=new_classes,
                         )
    dataset.save()

    if dataset.track_provenance():
        prov_str = f"Changed class column to {new_class_col}"
        mark_provenance(ProvenanceActivityType.MODIFIED, prov_str, dataset_dir)

        prov_str = f"Renamed previous class column to {new_name_for_current_class_col}"
        mark_provenance(ProvenanceActivityType.MODIFIED, prov_str, dataset_dir)


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

    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=class_list,
                         )
    dataset.save()

    if dataset.track_provenance():
        prov_str = f"Renamed class {old_class_name} to {new_class_name}"
        mark_provenance(ProvenanceActivityType.MODIFIED, prov_str, dataset_dir)


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
    dataset.set_multiple(metadata_headers=fields,
                         metadata_records=metadata,
                         classes=class_list,
                         )
    dataset.save()

    if dataset.track_provenance():
        if len(classes_to_merge) > 1:
            prefix = "es " + ", ".join(classes_to_merge)
        else:
            prefix = f" {classes_to_merge[0]}"
        prov_str = f"Merged class{prefix} into {target_class_name}"
        mark_provenance(ProvenanceActivityType.MODIFIED, prov_str, dataset_dir)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    classes()
