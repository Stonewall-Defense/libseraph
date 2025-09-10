###############################################################################
# Global Imports
###############################################################################
import json
import os
from uuid import uuid4

###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from ..lib.common import CLASSFILE_NAME, PREFERRED_METADATA_FILENAME, REQUIRED_METADATA_FIELD_NAMES, SERAPH_FILENAME
from ..lib.common import write_csv, write_json, get_input
from ..lib.history import HistoryManager


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


def _has_media_subtype(arg: str) -> bool:
    try:
        idx = arg.index("/")
        if idx == 1 or idx == len(arg) - 1:
            raise MediaTypeError(f"Invalid media type: {arg}")
        else:
            return True
    except ValueError:
        return False


###############################################################################
# ! Commands
###############################################################################
@click.command("init")
@click.option("--dataset_path", default=".")
@click.option("--override", default=False)
def init(dataset_path: str, override: bool):
    # Get the metadata fields from the user
    dataset_id = get_input("Enter a dataset ID: ")
    if not dataset_id:
        dataset_id = _get_uuid_uri()
        print(f"Setting random datset URI: {dataset_id}")

    dataset_name = get_input("Enter a human-readable dataset name: ",
                             valid_fn=_string_is_not_empty,
                             err_prompt="Dataset name cannot be an empty string",
                             )

    author_id = get_input("Enter your agent @id: ",
                          valid_fn=_string_is_not_empty,
                          err_prompt="Agent @id cannot be an empty string",
                          )

    # TODO: Support CRediT (https://credit.niso.org/) and DataCite (https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/contributor/#a-contributortype)
    author_rel = "associatedWith"

    media_type = get_input("Enter the dataset media type: ")
    if media_type and not _has_media_subtype(media_type):
        media_subtype = get_input("Enter the dataset media subtype: ")
    else:
        media_subtype = None

    license = get_input("Enter the dataset license: ")

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
        "author": {
            "uri": author_id,
            "rel": author_rel,
        },
        "keywords": keywords,
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


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    init()
