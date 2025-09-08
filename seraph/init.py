###############################################################################
# Global Imports
###############################################################################
from collections.abc import Callable
import json
import os
import pathlib
from typing import Optional
from uuid import uuid4

###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from .common import CLASSFILE_NAME, DATA_DIR, PREFERRED_METADATA_FILENAME, REQUIRED_METADATA_FIELD_NAMES, SERAPH_FILENAME, write_csv, write_json


###############################################################################
# Errors
###############################################################################
class MediaTypeError(Exception):
    pass


###############################################################################
# Helpers
###############################################################################
def _get_input(prompt: str,
               *,
               valid_fn: Optional[Callable[[str], bool]] = None,
               err_prompt="Invalid input",
               ) -> str:
    while True:
        user_input = input(prompt)
        is_valid = True
        if valid_fn is not None:
            is_valid = valid_fn(user_input)

        if is_valid:
            return user_input.strip()
        else:
            print(err_prompt)


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
    dataset_id = _get_input("Enter a dataset ID: ")
    if not dataset_id:
        dataset_id = _get_uuid_uri()
        print(f"Setting random datset URI: {dataset_id}")

    dataset_name = _get_input("Enter a human-readable dataset name: ",
                              valid_fn=_string_is_not_empty,
                              err_prompt="Dataset name cannot be an empty string",
                              )

    author_id = _get_input("Enter your agent @id: ",
                           valid_fn=_string_is_not_empty,
                           err_prompt="Agent @id cannot be an empty string",
                           )

    # TODO: Support CRediT (https://credit.niso.org/) and DataCite (https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/contributor/#a-contributortype)
    author_rel = "associatedWith"

    media_type = _get_input("Enter the dataset media type: ")
    if media_type and not _has_media_subtype(media_type):
        media_subtype = _get_input("Enter the dataset media subtype: ")
    else:
        media_subtype = None

    license = _get_input("Enter the dataset license: ")

    keywords = []
    keywork_input = "placeholder"
    while keywork_input:
        keywork_input = _get_input("Add keyword(s) to the dataset: ")
        if keywork_input:
            keywords.append(keywork_input)
    
    prov_tmp = _get_input("Track dataset provenance? [Y/n] ").strip()
    track_provenance = (not prov_tmp) or prov_tmp.lower() == "y"

    ver_tmp = _get_input("Track dataset version? [Y/n] ").strip()
    track_version = (not ver_tmp) or ver_tmp.lower() == "y"

    # Write the file
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

    if track_provenance or track_version:
        seraph_file_data["governance"] = {
            "provenance": track_provenance,
            "version": track_version,
        }

    fq_seraph_filename = os.path.join(dataset_path, SERAPH_FILENAME)
    with open(fq_seraph_filename, "x") as outfile:
        outfile.write(json.dumps(seraph_file_data, indent=2))

    fq_class_filename = os.path.join(dataset_path, CLASSFILE_NAME)
    if os.path.isfile(fq_class_filename) and not override:
        raise RuntimeError("Class file already exists")
    else:
        write_json(fq_class_filename, [])

    fq_metadata_filename = os.path.join(dataset_path, PREFERRED_METADATA_FILENAME)
    if os.path.isfile(fq_metadata_filename) and not override:
        raise RuntimeError("Metadata file already exists")
    else:
        write_csv(fq_metadata_filename, REQUIRED_METADATA_FIELD_NAMES, [])

    fq_data_dirname = os.path.join(dataset_path, DATA_DIR)
    pathlib.Path(fq_data_dirname).mkdir(parents=True, exist_ok=True)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    init()
