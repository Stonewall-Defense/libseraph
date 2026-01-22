###############################################################################
# Global Imports
###############################################################################
from collections.abc import Callable
import csv
from datetime import datetime, timezone
from enum import Enum
import json
import os
from typing import Optional, TypeVar

###############################################################################
# 3PP Imports
###############################################################################
from urllib.parse import urlparse


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
# Enums
###############################################################################
class VerifyOutputFormat(Enum):
    PRINT = "print"
    CSV = "csv"


VERIFY_OUTPUT_FORMATS = [val.value for val in VerifyOutputFormat]


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

REQUIRED_METADATA_IMPORT_COLS = ["original_dataset_uri", "license"]

VALID_MEDIA_TYPES = ["audio", "image", "multimedia", "text", "video"]


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


def get_user_input(prompt: str,
                   *,
                   valid_fn: Optional[Callable[[str], bool]] = None,
                   err_prompt="Invalid input",
                   ) -> str | None:
    while True:
        user_input = input(prompt)
        is_valid = True
        if valid_fn is not None:
            is_valid = valid_fn(user_input)

        if is_valid:
            return user_input.strip()
        else:
            print(err_prompt)


def now():
    return datetime.now(timezone.utc)


def now_str():
    return format_iso_date(now())


def today():
    return datetime.now().strftime("%Y-%m-%d")


def parse_iso_date(date_string: str):
    return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%SZ")


def format_iso_date(dt: datetime):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_web_url(val: str) -> bool:
    parsed = urlparse(val)
    return parsed.scheme.startswith("http") and bool(parsed.netloc)
