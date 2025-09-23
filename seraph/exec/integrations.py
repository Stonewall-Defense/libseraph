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
from ..lib import SeraphDataset, write_json, load_license, is_web_url


###############################################################################
# Constants
###############################################################################
CLASS_NAME_REPLACE_PATTERN = re.compile(r'[^\w\s]')


###############################################################################
# ! Commands
###############################################################################
@click.group("integrations")
def integrations():
    pass


# See https://datatracker.ietf.org/doc/html/rfc8493
@integrations.command("bagit")
@click.option("--dataset_path", default=".")
@click.option("--namaste", is_flag=True)
def bagit(dataset_path: str, namaste: bool):
    try:
        from FreezeTag import bag_and_tag
    except ImportError:
        print("[red]For BagIt integration `seraph` relies on the FreezeTag library, which is not installed[/red]")
        sys.exit(1)

    dataset = SeraphDataset(dataset_path)

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

    bag_and_tag(dataset_path, metadata=bag_meta, other_tag_files=seraph_tagfiles, write_namaste=namaste)


@integrations.command("datapackage")
@click.option("--dataset_path", default=".")
@click.option("--output_filename", default="datapackage.json")
def datapackage(dataset_path: str, output_filename: str):
    dataset = SeraphDataset(dataset_path)
    seraph_meta = dataset.get_seraph_metadata()

    # Core metadata
    package: dict[str, Any] = {
        "id": seraph_meta.uri,
        "name": seraph_meta.name,
        "version": seraph_meta.version,
        "created": seraph_meta.creationDate.strftime("%Y-%m-%dT%H:%M:%SZ"),
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

    fq_output_filename = os.path.join(dataset_path, output_filename)
    write_json(fq_output_filename, package)


@integrations.command("fuelai")
@click.option("--dataset_path", default=".")
@click.option("--force", is_flag=True)
def fuelai(dataset_path: str, force: bool):
    dataset = SeraphDataset(dataset_path)
    classes = dataset.get_classes()

    mod_classes = [c for c in classes if re.search(CLASS_NAME_REPLACE_PATTERN, c) is not None]
    if mod_classes:
        mod_str = f"Classes {', '.join(mod_classes)} {'will' if force else 'would'} be modified during the export process"
        if force:
            warnings.warn(mod_str)
        else:
            raise ValueError(mod_str)

    fuelai_classes = [{"name": re.sub(CLASS_NAME_REPLACE_PATTERN, "_", c)} for c in classes]
    write_json("fuelai-classes.json", fuelai_classes)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    integrations()
