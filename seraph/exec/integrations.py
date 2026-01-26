###############################################################################
# Global Imports
###############################################################################
import os
import re
import sys
from typing import Any
import warnings

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print

###############################################################################
# Local Imports
###############################################################################
from ..lib import SeraphDataset, ChangeRecord, VersionBumpType, ChangeType, write_json, load_license, is_web_url, format_iso_date, read_json


###############################################################################
# Constants
###############################################################################
CLASS_NAME_REPLACE_PATTERN = re.compile(r'[^\w\s]')


###############################################################################
# ! Commands
###############################################################################
@click.group("integrations", help="[EXPERIMENTAL] Import/export to 3PP data management formats")
def integrations():
    pass


# See https://datatracker.ietf.org/doc/html/rfc8493
@integrations.command("bagit", help="https://datatracker.ietf.org/doc/html/rfc8493")
@click.option("--dataset_dir", default=".")
@click.option("--namaste", is_flag=True)
def bagit(dataset_dir: str, namaste: bool):
    try:
        from FreezeTag import bag_and_tag
    except ImportError:
        print("[red]For BagIt integration `seraph` relies on the FreezeTag library, which is not installed[/red]")
        sys.exit(1)

    dataset = SeraphDataset(dataset_dir)

    # TODO: Org details, `External-Description`
    seraph_meta = dataset.get_seraph_metadata()
    bag_meta = [
        ("External-Identifier", seraph_meta.uri),
        ("Dataset-Name", seraph_meta.name),         # Nonstandard but allowed
    ]

    for author in seraph_meta.authors:
        bag_meta.append(("Contact-Name", author.name))
        if author.email:
            bag_meta.append(("Contact-Email", author.email))

    seraph_tagfiles = [
        dataset.get_class_filename(),
        dataset.get_metadata_filename(),
        dataset.get_seraph_filename(),
    ]

    bag_and_tag(dataset_dir, metadata=bag_meta, other_tag_files=seraph_tagfiles, write_namaste=namaste)


@integrations.group("datapackage", help="https://datapackage.org/standard/data-package/")
def datapackage():
    pass


@datapackage.command("export")
@click.option("--dataset_dir", default=".")
@click.option("--output_filename", default="datapackage.json")
def datapackage_export(dataset_dir: str, output_filename: str):
    dataset = SeraphDataset(dataset_dir)
    seraph_meta = dataset.get_seraph_metadata()

    # Core metadata
    package: dict[str, Any] = {
        "id": seraph_meta.uri,
        "name": seraph_meta.name,
        "version": seraph_meta.version,
        "created": format_iso_date(seraph_meta.creationDate),
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
    }

    if seraph_meta.keywords:
        package["keywords"] = seraph_meta.keywords

    # License conversion
    license = load_license(seraph_meta.license) if seraph_meta.license else None
    if not license:
        print("[red]DataPackages must have an open license[/red]")
        sys.exit(1)

    package["licenses"] = [
        {
            "name": license.id,
            "path": license.url,
            "title": license.title,
        }
    ]

    # Author conversion
    contributors = []
    for author in seraph_meta.authors:
        c = {
            "title": author.name,
            "givenName": author.givenName,
        }

        if author.givenName:
            c["givenName"] = author.givenName

        if author.familyName:
            c["familyName"] = author.familyName

        if is_web_url(author.uri):
            c["path"] = author.uri

        if author.email:
            c["email"] = author.email

        # "A role is RECOMMENDED to follow an established vocabulary, such as DataCite Metadata Schema’s contributorRole or CRediT."
        c["roles"] = list(set([("ProjectMember" if r == "associatedWith" else r) for r in author.roles]))

        contributors.append(c)
    if contributors:
        package["contributors"] = contributors

    # History conversion
    history = dataset.get_history()
    raw_sources = history.load_sources()
    sources = []
    for source in raw_sources:
        s = {
            "title": source.name,
            "path": source.uri,
            "version": source.version,
        }
        sources.append(s)
    if sources:
        package["sources"] = sources

    # Resource conversion
    # TODO: Properly support entries for all data files
    package["resources"] = [{
        "name": "metadata",
        "path": dataset.get_metadata_filename(),
        "title": "Dataset Metadata File",
        "format": "csv",
        "mediatype": "text/csv",
        "encoding": "utf-8",
    }]

    fq_output_filename = os.path.join(dataset_dir, output_filename)
    write_json(fq_output_filename, package)


@click.option("--dataset_dir", default=".")
@click.option("--input_filename", default="datapackage.json")
@datapackage.command("import")
def datapackage_import(dataset_dir: str, input_filename: str):
    try:
        SeraphDataset.directory_is_seraph_dataset(dataset_dir)
        print(f"[red]Directory {dataset_dir} is already a Seraph dataset and will not be overwritten")
        sys.exit(1)
    except ValueError:
        pass

    print("[yellow]Sorry, this isn't implemented yet[/yellow]")


@integrations.group("rocrate", help="https://www.researchobject.org/ro-crate/specification/1.2/index.html")
def rocrate():
    pass


@rocrate.command("export")
@click.option("--dataset_dir", default=".")
@click.option("--preview", is_flag=True)
def rocrate_export(dataset_dir: str, preview: bool):
    try:
        from rocrate.rocrate import ROCrate
        from rocrate.model.person import Person
    except ImportError:
        print("[red]For RO-Crate integration `seraph` relies on the `rocrate` library, which is not installed[/red]")
        sys.exit(1)

    dataset = SeraphDataset(dataset_dir)

    crate = ROCrate(gen_preview=preview)
    crate.add_file(dataset.get_seraph_filename(), properties={
        "name": "Seraph File",
        "encodingFormat": "application/json",
    })
    crate.add_file(dataset.get_metadata_filename(), properties={
        "name": "Metadata File",
        "encodingFormat": "text/csv",
    })
    crate.add_file(dataset.get_class_filename(), properties={
        "name": "Class List File",
        "encodingFormat": "application/json",
    })

    seraph = dataset.get_seraph_metadata()

    crate.name = seraph.name
    crate.license = seraph.license

    for a in seraph.authors:
        crate.add(Person(crate, a.uri, properties={
            "name": a.name,
        }))

    crate.add_dataset(dataset.get_data_dir())

    crate.write(dataset_dir)


@integrations.group("fuelai", help="https://fuelai.lotl.app/")
def fuelai():
    pass


@fuelai.command("export", help="Export Seaph `classes.json` file to FuelAI format")
@click.option("--dataset_dir", default=".", help="Root DIR of the Seraph dataset to export")
@click.option("--force", is_flag=True, help="Replace non-word characters with `_` IAW FuelAI naming requirements")
@click.option("--drop_leading_underscore", is_flag=True, help="If replacing class name characters, should a potential leading `_` be dropped?")
def fuelai_export(dataset_dir: str, force: bool, drop_leading_underscore: bool):
    dataset = SeraphDataset(dataset_dir)
    classes = dataset.get_classes()

    mod_classes = [c for c in classes if re.search(CLASS_NAME_REPLACE_PATTERN, c) is not None]
    if mod_classes:
        mod_str = f"Classes {', '.join(mod_classes)} {'will' if force else 'would'} be modified during the export process"
        if force:
            warnings.warn(mod_str, stacklevel=2)
        else:
            raise ValueError(mod_str)

    classes_tmp = [re.sub(CLASS_NAME_REPLACE_PATTERN, "_", c) for c in classes]
    if drop_leading_underscore:
        classes_tmp = [re.sub(r'^_', "", c) for c in classes_tmp]

    fuelai_classes = [{"name": c} for c in classes_tmp]

    fq_output_filename = os.path.join(dataset_dir, "fuelai-classes.json")
    write_json(fq_output_filename, fuelai_classes)


@fuelai.command("import")
@click.option("--dataset_dir", default=".")
@click.option("--fuelai_metadata_file", required=True)
@click.option("--sort_classes", is_flag=True)
@click.option("--force", is_flag=True)
def fuelai_import(dataset_dir: str, fuelai_metadata_file: str, sort_classes: bool, force: bool):
    try:
        SeraphDataset.directory_is_seraph_dataset(dataset_dir)
        new_dataset = False
    except ValueError:
        new_dataset = True

    if new_dataset:
        print("[yellow]Sorry, this isn't implemented yet[/yellow]")
    else:
        dataset = SeraphDataset(dataset_dir)
        classes = dataset.get_classes()
        if len(classes) > 0 and not force:
            print("[yellow]Dataset already has classes listed; to append to existing class list, retry with `--force` flag[/yellow]")
            return
        else:
            fuelai_raw = read_json(fuelai_metadata_file)
            fuel_ai_classes = [c["name"] for c in fuelai_raw]
            classes += fuel_ai_classes

            if sort_classes:
                classes.sort()

            change = ChangeRecord(
                bump_type=VersionBumpType.MAJOR,
                change_type=ChangeType.ADD,
                message=f"Added {len(fuel_ai_classes)} from FuelAI metadata file"
            )
            dataset.set_classes(classes, change_record=change).save()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    integrations()
