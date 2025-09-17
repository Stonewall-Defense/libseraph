###############################################################################
# Global Imports
###############################################################################
from itertools import zip_longest
import json
import os
from uuid import uuid4

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print
from rich.table import Table

###############################################################################
# Local Imports
###############################################################################
from ..lib import CLASSFILE_NAME, PREFERRED_METADATA_FILENAME, REQUIRED_METADATA_FIELD_NAMES, SERAPH_FILENAME, VERIFY_OUTPUT_FORMATS, VALID_MEDIA_TYPES
from ..lib import write_csv, write_json, get_input, str_to_enum, now, load_license, print_license_concerns
from ..lib import HistoryManager, VerifyOutputFormat, SeraphDataset, ChangeRecord, VersionBumpType, ChangeType


###############################################################################
# Errors
###############################################################################
class MediaTypeError(Exception):
    pass


###############################################################################
# Helpers
###############################################################################
def _get_uuid_uri():
    return f"urn:uuid:{uuid4()}"


def _string_is_not_empty(arg: str) -> bool:
    return len(arg.strip()) > 0


def _media_type_is_valid(arg: str) -> bool:
    return any([arg.startswith(m) for m in VALID_MEDIA_TYPES])


def _has_media_subtype(arg: str) -> bool:
    try:
        idx = arg.index("/")
        if idx == 0 or idx == len(arg) - 1:
            raise MediaTypeError(f"Invalid media type: {arg}")
        else:
            return True
    except ValueError:
        return False


def _get_media_type_from_user():
    media_type, media_subtype = None, None
    has_media_subtype = False

    while True:
        media_type = get_input("Enter the dataset media type: ", valid_fn=_media_type_is_valid, err_prompt=f"Media type must be one of: {VALID_MEDIA_TYPES}")
        if not media_type:
            continue

        has_media_subtype = _has_media_subtype(media_type)
        if media_type.startswith("multimedia") and has_media_subtype:
            print("Multimedia datasets MUST NOT specify a `mediaSubtype`")
            continue
        else:
            break


    if media_type and not _has_media_subtype(media_type):
        media_subtype = get_input("Enter the dataset media subtype: ")
    
    return media_type, media_subtype


def _get_license_from_user():
    license = None
    while license is None:
        license = get_input("Enter the dataset license: ", valid_fn=_string_is_not_empty, err_prompt="A dataset must have a license")

    lookup = load_license(license)
    print_license_concerns(lookup)
    return license


# TODO: Finish this!
def _get_authors_from_user():
    authors = []
    have_author_data = True
    while have_author_data and not authors:
        author_id = get_input("Enter author URI: " if not authors else "Enter another author URI (optional): ",
                              valid_fn=_string_is_not_empty,
                              err_prompt="author URI cannot be an empty string",
                              )
        if not author_id:
            continue

        author_metadata = _process_author_uri(author_id)
        if not author_metadata:
            author_name = ""
            while not author_name:
                author_name = get_input("Enter Author Name: ", valid_fn=_string_is_not_empty, err_prompt="Author name cannot be empty")
        else:
            author_name = ""
            pass    # TODO: Add this feature

        author_roles = []
        author_role = ""
        # TODO: Support CRediT (https://credit.niso.org/) and DataCite (https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/contributor/#a-contributortype)
        while not author_roles or author_role and author_role != "associatedWith":
            author_role = get_input(f"Add author role {'(default: `associatedWith`)' if not author_roles else '(optional)'}: ")
            if not author_role and not author_roles:
                author_role = "associatedWith"
            if author_role:
                author_roles.append(author_role)

        authors.append({
            "uri": author_id,
            "name": author_name,
            "roles": author_roles,
        })


def _process_author_uri(uri: str):
    if uri.startswith("http"):
        # ORCID, ISNI, vCard, hCard, jCard, FOAF
        print("[orange]One day we'll support HTTP lookup ...[/orange]")
    elif os.path.isfile(uri):
        # vCard, hCard, jCard, FOAF
        print("[orange]One day we'll support file parsing ...[/orange]")
    else:
        print("[red]No plans to support `tag` URIs[/red]")

    return None


###############################################################################
# ! Commands
###############################################################################
@click.group("meta")
def meta():
    pass


@meta.command("init")
@click.option("--dataset_path", default=".")
@click.option("--override", default=False)
def meta_init(dataset_path: str, override: bool):
    # Get the core metadata fields from the user
    dataset_id = get_input("Enter a dataset ID: ")
    if not dataset_id:
        dataset_id = _get_uuid_uri()
        print(f"Setting random datset URI: {dataset_id}")

    dataset_name = get_input("Enter a human-readable dataset name: ",
                             valid_fn=_string_is_not_empty,
                             err_prompt="Dataset name cannot be an empty string",
                             )

    # Media type validation logic is a bit more complex
    media_type, media_subtype = _get_media_type_from_user()

    # License checking logic is a bit more complex
    license = _get_license_from_user()

    # Author logic is much more complex
    authors = _get_authors_from_user()

    # Zero or more keywords, but no restrictions on them
    keywords = []
    keywork_input = "placeholder"
    while keywork_input:
        keywork_input = get_input("Add keyword(s) to the dataset: ")
        if keywork_input:
            keywords.append(keywork_input)

    # Compose the data
    seraph_file_data = {
        "uri": dataset_id,
        "version": "v0.0.0",
        "name": dataset_name,
        "authors": authors,
        "keywords": keywords,
        "creationDate": now(),
    }

    if media_type:
        seraph_file_data["mediaType"] = media_type

    if media_subtype:
        seraph_file_data["mediaSubtype"] = media_subtype

    if license:
        seraph_file_data["license"] = license

    # Write the file itself
    fq_seraph_filename = os.path.join(dataset_path, SERAPH_FILENAME)
    with open(fq_seraph_filename, "x") as outfile:
        outfile.write(json.dumps(seraph_file_data, indent=2))

    # Empty `classes.json` file
    fq_class_filename = os.path.join(dataset_path, CLASSFILE_NAME)
    if os.path.isfile(fq_class_filename) and not override:
        raise RuntimeError("Class file already exists")
    else:
        write_json(fq_class_filename, [])

    # Placeholder `metadata.csv` file
    fq_metadata_filename = os.path.join(dataset_path, PREFERRED_METADATA_FILENAME)
    if os.path.isfile(fq_metadata_filename) and not override:
        raise RuntimeError("Metadata file already exists")
    else:
        write_csv(fq_metadata_filename, REQUIRED_METADATA_FIELD_NAMES, [])

    # Ensure necessary dirs exists
    HistoryManager.initialize(dataset_path)


@meta.command("verify")
@click.option("--dataset_path", default=".")
@click.option("--output_format", default="print", type=click.Choice(VERIFY_OUTPUT_FORMATS))
def meta_verify(dataset_path: str, output_format: str):
    dataset = SeraphDataset(dataset_path)

    headers, _ = dataset.get_metadata()

    fmt = str_to_enum(output_format, VerifyOutputFormat)

    missing_headers = []
    dupe_headers = []

    headers_seen = set()

    for h in headers:
        if h in headers_seen:
            dupe_headers.append(h)
        else:
            headers_seen.add(h)

    for h in REQUIRED_METADATA_FIELD_NAMES:
        if h not in headers:
            missing_headers.append(h)

    if not missing_headers and not dupe_headers:
        print("[bold green]No metadata column issues[bold green]")
    else:
        COLUMNS = ["missing_headers", "dupe_headers"]
        if fmt == VerifyOutputFormat.CSV:
            write_csv("metadata-verification-errors.csv",
                      COLUMNS,
                      [{"missing_headers": m, "dupe_headers": d} for m, d in zip_longest(missing_headers, dupe_headers)])
        else:
            table = Table(
                *COLUMNS,
                title="Metadata Issues"
            )

            for m, d in zip_longest(missing_headers, dupe_headers):
                table.add_row(m, d)
            print(table)


@meta.command("dataum-id")
@click.option("--dataset_path", default=".")
@click.option("--datum_col_name", default="datum_id")
@click.option("--start_from_1", is_flag=True)
def meta_datum_id(dataset_path: str, datum_col_name: str, start_from_1: bool):
    dataset = SeraphDataset(dataset_path)

    headers, records = dataset.get_metadata()

    if datum_col_name not in headers:
        headers.insert(0, datum_col_name)

    datum_id = 1 if start_from_1 else 0
    for record in records:
        record[datum_col_name] = str(datum_id)
        datum_id += 1

    # Save the dataset
    change = ChangeRecord(
        bump_type=VersionBumpType.MINOR,
        change_type=ChangeType.CHANGE,
        message=f"Added metadata column for datum_id: {datum_col_name}"
    )
    dataset.set_metadata_headers(headers, change_record=change).set_metadata_records(records).save()


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    meta()
