###############################################################################
# Global Imports
###############################################################################
import csv
from enum import Enum
import os
from typing import Optional


###############################################################################
# Local Imports
###############################################################################
from .common import str_to_enum


###############################################################################
# Enums
###############################################################################
class SupportedMediaType(Enum):
    AUDIO = "audio"
    IMAGE = "image"
    TEXT = "text"
    VIDEO = "video"
    MULTIMEDIA = "multimedia"


class MediaTypeTree(Enum):
    VND = "vnd"
    PRS = "prs"
    X = "x"


SUPPORTED_MEDIA_TYPES = [val.value for val in SupportedMediaType]
MEDIA_TYPE_TREES = [val.value for val in MediaTypeTree]


###############################################################################
# Constants
###############################################################################
_DIR_PATH = os.path.dirname(os.path.realpath(__file__))
_MEDIA_TYPE_FOLDER = os.path.join(_DIR_PATH, "data/media_types")


###############################################################################
# Config
###############################################################################
_MEDIA_TYPE_SUBTYPE_MAP: dict[SupportedMediaType, list[str]] = {}


###############################################################################
# Helpers
###############################################################################
def _load_subtypes_for_media_type(media_type: str):
    filename = os.path.join(_MEDIA_TYPE_FOLDER, f"{media_type}.csv")
    with open(filename, "r") as infile:
        reader = csv.DictReader(infile)
        return [line["Template"].split("/")[1] for line in reader]


def _has_media_subtype(arg: str) -> bool:
    try:
        idx = arg.index("/")
        if idx == 0 or idx == len(arg) - 1:
            raise ValueError(f"Invalid media type: {arg}")
        else:
            return True
    except ValueError:
        return False


def _supports_subtype(media_type: SupportedMediaType):
    return media_type != SupportedMediaType.MULTIMEDIA


###############################################################################
# Functions
###############################################################################
def check_media_type(media_type: str,
                     media_subtype: Optional[str] = None,
                     *,
                     allowed_media_type_trees: list[MediaTypeTree] = [MediaTypeTree.VND],
                     ):
    # Deal with possible subtype issues/configurations
    has_media_subtype = _has_media_subtype(media_type)
    if has_media_subtype and media_subtype:
        raise ValueError("Cannot supply a media subtype in but the media type and separately")
    elif has_media_subtype:
        segs = media_type.split("/")
        if len(segs) != 2:
            raise ValueError(media_type)
        media_type, media_subtype = media_type.split("/")

    # Deal w/ media type verification
    media_fmt = str_to_enum(media_type, SupportedMediaType)
    if media_subtype and not _supports_subtype(media_fmt):
        raise ValueError(f"Submitted media type ({media_type}) does not support subtypes; got `{media_subtype}`")

    # If no subtype, no need to verify
    if not media_subtype:
        return media_type, media_subtype

    # Lazy load
    if media_type not in _MEDIA_TYPE_SUBTYPE_MAP:
        _MEDIA_TYPE_SUBTYPE_MAP[media_fmt] = _load_subtypes_for_media_type(media_type)

    possible_media_subtypes = _MEDIA_TYPE_SUBTYPE_MAP[media_fmt]
    if media_subtype not in possible_media_subtypes:
        raise ValueError(f"{media_subtype} is not a valid subtype of media type {media_type}")

    # Check subtype trees
    segs = media_subtype.split(".")
    has_tree = len(segs) > 1
    if not has_tree:
        return media_type, media_subtype

    tree = segs[0]
    allowed = [t.value for t in allowed_media_type_trees]
    if tree not in allowed:
        raise ValueError(f"Subtype tree {tree} is not allowed, must in the standards tree or be one of {allowed}")
    else:
        return media_type, media_subtype
