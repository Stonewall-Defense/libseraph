###############################################################################
# Global Imports
###############################################################################
import csv
from enum import Enum
import json
import os
from typing import TypeVar


###############################################################################
# Types and Classes
###############################################################################
T = TypeVar("T", bound=Enum)


###############################################################################
# Errors
###############################################################################
class EnumArgumentError(Exception):
    pass


###############################################################################
# Constants
###############################################################################
SERAPH_INTERNAL_DIR = ".seraph"

CLASSFILE_NAME = "classes.json"
SERAPH_FILENAME = "seraph.json"
PREFERRED_METADATA_FILENAME = "metadata.csv"

ALLOWED_METADATA_FILENAMES = [
    "meta.csv",
    "metadata.csv",
]

DATA_DIR = "data"

REQUIRED_METADATA_FIELD_NAMES = ["class_id", "class_name", "filename"]


###############################################################################
# Helpers
###############################################################################
def get_metadata_filename(dir: str):
    return "meta.csv" if "meta.csv" in os.listdir(dir) else PREFERRED_METADATA_FILENAME


def read_csv(fq_filename: str) -> tuple[list[str], list[dict[str, str]]]:
    with open(fq_filename, "r") as infile:
        reader = csv.DictReader(infile)

        field_names = [f for f in reader.fieldnames] if reader.fieldnames else []
        lines = [line for line in reader]

        return field_names, lines


def write_csv(fq_filename: str, headers: list[str], data: list[dict]):
    with open(fq_filename, "w") as outfile:
        writer = csv.DictWriter(outfile, headers)
        writer.writeheader()
        writer.writerows(data)


def read_json(fq_filename: str):
    with open(fq_filename, "r") as infile:
        return json.loads(infile.read())


def write_json(fq_filename: str, data: list | dict, indent=2):
    with open(fq_filename, "w") as outfile:
        outfile.write(json.dumps(data, indent=indent))


def str_to_enum(arg: str, target_enum: type[T]) -> T:
    try:
        return target_enum(arg)
    except KeyError:
        raise EnumArgumentError(f"Invalid value {arg} for enumerated type {type(target_enum)}; must be one of {[val.name for val in target_enum]}")
