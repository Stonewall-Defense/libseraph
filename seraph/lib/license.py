###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
from enum import Enum
import os
from typing import Optional

###############################################################################
# 3PP Imports
###############################################################################
from rich import print

###############################################################################
# Local Imports
###############################################################################
from .common import read_json, is_web_url, str_to_enum


###############################################################################
# Enums
###############################################################################
class LicenseStatus(Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class LicenseConformance(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_REVIEWED = "not reviewed"


###############################################################################
# Classes
###############################################################################
@dataclass(kw_only=True)
class License:
    id: str
    title: str
    url: str

    od_conformance: LicenseConformance
    osd_conformance: LicenseConformance
    status: LicenseStatus
    is_of_concern: bool


###############################################################################
# Config
###############################################################################
_DIR_PATH = os.path.dirname(os.path.realpath(__file__))
_LICENSES_PATH = os.path.join(_DIR_PATH, "licenses.json")

ALL_LICENSES: list[dict[str, str]] = read_json(_LICENSES_PATH).values()


###############################################################################
# Helpers
###############################################################################
def _license_is_of_concern(od_conformance: LicenseConformance, osd_conformance: LicenseConformance, status: LicenseStatus):
    return od_conformance != LicenseConformance.APPROVED or osd_conformance != LicenseConformance.APPROVED or status != LicenseStatus.ACTIVE


def _conf_str(conf: LicenseConformance):
    if conf == LicenseConformance.APPROVED:
        return ""
    elif conf == LicenseConformance.NOT_REVIEWED:
        return "[yellow]NOT REVIEWED[/yellow]"
    else:
        return "[red]REJECTED[/red]"


def _stat_str(stat: LicenseStatus):
    if stat == LicenseStatus.ACTIVE:
        return ""
    elif stat == LicenseStatus.SUPERSEDED:
        return "[yellow]SUPERSEDED[/yellow]"
    else:
        return "[red]RETIRED[/red]"


def _format_license_concerns(license: Optional[License]) -> str:
    if not license:
        return "[yellow]WARNING: That license is not registered with https://opendefinition.org/[/yellow]"

    ret = " > Possible license concerns: "

    od_concern = _conf_str(license.od_conformance)
    od_concern = f"Open Definition conformance is {od_concern}" if od_concern else ""

    osd_concern = _conf_str(license.osd_conformance)
    osd_concern = f"OSI conformance is {osd_concern}" if osd_concern else ""

    status_concern = _stat_str(license.status)
    status_concern = f"license status is {status_concern}" if status_concern else ""

    ret += ", ".join([c for c in [od_concern, osd_concern, status_concern] if c])
    return ret


###############################################################################
# Functions
###############################################################################
def load_license(license_id: str) -> Optional[License]:
    key = "url" if is_web_url(license_id) else "id"
    raw_license = next((l for l in ALL_LICENSES if l[key] == license_id), None)

    if raw_license:
        od_conformance = str_to_enum(raw_license["od_conformance"] or "not reviewed", LicenseConformance)
        osd_conformance = str_to_enum(raw_license["osd_conformance"] or "not reviewed", LicenseConformance)
        status = str_to_enum(raw_license["status"], LicenseStatus)
        is_of_concern = _license_is_of_concern(od_conformance, osd_conformance, status)

        return License(
            id=raw_license["id"],
            title=raw_license["title"],
            url=raw_license["url"],

            od_conformance=od_conformance,
            osd_conformance=osd_conformance,
            status=status,
            is_of_concern=is_of_concern,
        )
    else:
        return None


def print_license_concerns(license: Optional[License]) -> None:
    if license and not license.is_of_concern:
        return
    else:
        print(_format_license_concerns(license))
