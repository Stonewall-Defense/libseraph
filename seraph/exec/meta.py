###############################################################################
# Global Imports
###############################################################################
from dataclasses import asdict
from itertools import zip_longest
from typing import Optional
from uuid import uuid4

###############################################################################
# 3PP Imports
###############################################################################
import click
from rich import print
from rich.table import Table

###############################################################################
# Certus Imports
###############################################################################
from asaperson import orcid_to_person, isni_to_person, vcf_to_person

###############################################################################
# Local Imports
###############################################################################
from ..lib import REQUIRED_METADATA_FIELD_NAMES, VERIFY_OUTPUT_FORMATS, VALID_MEDIA_TYPES, DEFAULT_AUTHOR_ROLE
from ..lib import write_csv, get_user_input, str_to_enum, now, load_license, print_license_concerns, check_role_in_known_taxonomy, uri_to_identifier_schema, check_media_type, derive_dataset
from ..lib import HistoryManager, VerifyOutputFormat, SeraphDataset, ChangeRecord, VersionBumpType, ChangeType, DatasetAuthor, RoleTaxonomy, SupportedMediaType


###############################################################################
# Helpers
###############################################################################
def _get_uuid_uri():
    return f"urn:uuid:{uuid4()}"


def _string_is_not_empty(arg: str) -> bool:
    return len(arg.strip()) > 0


def _get_media_type_from_user() -> tuple[SupportedMediaType, Optional[str]]:
    media_type, media_subtype = None, None

    while True:
        media_type = get_user_input("Enter the dataset media type: ", valid_fn=_string_is_not_empty, err_prompt=f"Media type must be one of: {VALID_MEDIA_TYPES}")
        if not media_type:
            continue

        try:
            media_type, media_subtype = check_media_type(media_type)
            break
        except ValueError as e:
            print(f"[red]{format(e)}[/red]")
            continue

    if not media_subtype:
        media_subtype = get_user_input("Enter the dataset media subtype: ")

    return media_type, media_subtype


def _get_license_from_user():
    license = None
    while license is None:
        license = get_user_input("Enter the dataset license: ", valid_fn=_string_is_not_empty, err_prompt="A dataset must have a license")

    lookup = load_license(license)
    print_license_concerns(lookup)
    return license


def _process_author_uri(uri: str):
    author = None

    if "orcid" in uri:
        try:
            author = orcid_to_person(uri)
        except ValueError:
            print(f"[red]Unable to dereference probable ORCID {uri}[/red]")
    elif "isni" in uri:
        try:
            author = isni_to_person(uri)
        except ValueError:
            print(f"[red]Unable to dereference probable ISNI {uri}[/red]")
    elif uri.startswith("urn:uuid") or uri.startswith("tag"):
        pass    # This is fine; these can't be dereferenced
    else:
        try:
            author = vcf_to_person(uri)
        except ValueError:
            print(f"[yellow]Unknown author URI {uri} is not a VCF[/yellow]")

    return author


def _get_authors_from_user():
    authors: list[DatasetAuthor] = []
    have_author_data = True
    while have_author_data and not authors:
        # Get an ID or bail on the rest of the loop
        author_id = get_user_input("Enter author URI: " if not authors else "Enter another author URI (optional): ",
                                   valid_fn=_string_is_not_empty,
                                   err_prompt="Author URI cannot be an empty string",
                                   )
        if not author_id:
            continue

        # Can this be cleaned up at all? We have to wait to assemble the DatasetAuthor object until after role(s) are assigned ...
        author_metadata = _process_author_uri(author_id)
        if not author_metadata:
            author_name = ""
            while not author_name:
                author_name = get_user_input("Enter Author Name: ", valid_fn=_string_is_not_empty, err_prompt="Author name cannot be empty")
        else:
            author_name = ""    # Placeholder, not used

        # Assign roles, prferably from a known list
        author_roles = []
        author_role = ""

        # Continue until we have something OR we have at least one non-default role and they give us nothing
        while not author_roles or (author_role and author_role != DEFAULT_AUTHOR_ROLE):
            author_role = get_user_input(f"Add author role {f'(default: `associatedWith`)' if not author_roles else '(optional)'}: ")

            # Apply default iff no existing role
            if not author_role and not author_roles:
                author_role = DEFAULT_AUTHOR_ROLE

            # If not default, prompt if this may not be the best option
            if author_role and author_role != DEFAULT_AUTHOR_ROLE:
                role_type = check_role_in_known_taxonomy(author_role)
                if role_type == RoleTaxonomy.NONE:
                    print("[yellow]WARNING: Prefer roles from known taxonomies such as CRediT or DataCite[/yellow]")

            # Save the role iff we have a role
            if author_role:
                author_roles.append(author_role)

        authors.append(DatasetAuthor(
            # Necessary fields
            uri=author_id,
            name=author_metadata.name if author_metadata else author_name,
            roles=author_roles,

            # Optional fields
            givenName=author_metadata.given_name if author_metadata else None,
            familyName=author_metadata.family_name if author_metadata else None,
            identifierScheme=uri_to_identifier_schema(author_id),
            email=author_metadata.email if author_metadata else None,
            affiliations=None
        ))

    return authors


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
    dataset_id = get_user_input("Enter a dataset ID: ")
    if not dataset_id:
        dataset_id = _get_uuid_uri()
        print(f"Setting random datset URI: {dataset_id}")

    dataset_name = get_user_input("Enter a human-readable dataset name: ",
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
        keywork_input = get_user_input(f"Add {'more ' if keywords else ''}keyword(s) to the dataset: ")
        if keywork_input:
            keywords.append(keywork_input)

    # Compose the data
    seraph_file_data = {
        "uri": dataset_id,
        "version": "v0.0.0",
        "name": dataset_name,
        "authors": [asdict(a) for a in authors],
        "keywords": keywords,
        "creationDate": now(),
    }

    if media_type:
        seraph_file_data["mediaType"] = media_type.value

    if media_subtype:
        seraph_file_data["mediaSubtype"] = media_subtype

    if license:
        seraph_file_data["license"] = license

    # Write the file itself
    SeraphDataset.create(dataset_path, seraph_file_data, override)

    # Ensure necessary dirs exists
    HistoryManager.initialize(dataset_path)


@meta.command("derive")
@click.option("--dataset_path", default=".")
@click.option("--parent_dataset", required=True)
@click.option("--uri", required=True)
def meta_derive(dataset_path: str, parent_dataset: str, uri: str):
    parent = SeraphDataset(parent_dataset)
    derive_dataset(parent, dataset_path, uri)


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
