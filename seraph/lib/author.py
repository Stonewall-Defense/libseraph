###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
from enum import Enum
from typing import Optional


###############################################################################
# Enums
###############################################################################
class NameIdentifierScheme(Enum):
    ORCID = "ORCID"
    ISNI = "ISNI"
    ROR = "ROR"
    TAG = "tag"
    UUID = "UUID"


class RoleTaxonomy(Enum):
    CREDIT = "CRediT"
    DATACITE = "DataCite"
    NONE = "None"


###############################################################################
# Data Classes
###############################################################################
@dataclass
class Organization:
    uri: str
    name: str

    address: Optional[str]
    identifierScheme: Optional[str]


@dataclass(kw_only=True)
class DatasetAuthor:
    # Necessary fields for DataCite and Frictionless DataPackage
    uri: str
    name: str
    roles: list[str]

    # Helpful fields for authors
    givenName: Optional[str]
    familyName: Optional[str]
    identifierScheme: Optional[str]
    email: Optional[str]
    affiliations: Optional[list[Organization]]


###############################################################################
# Constants
###############################################################################

# https://credit.niso.org/
CREDIT_ROOT_URL = "https://credit.niso.org/contributor-roles/"

# See https://groups.niso.org/higherlogic/ws/public/download/26466/ANSI-NISO-Z39.104-2022.pdf
CREDIT_ROLES = [
    "conceptualization",
    "data-curation",
    "formal-analysis",
    "funding-acquisition",
    "investigation",
    "methodology",
    "project-administration",
    "resources",
    "software",
    "supervision",
    "validation",
    "visualization",
    "writing-original-draft",
    "writing-review-editing",
]

# See https://jats4r.niso.org/credit-taxonomy/
CREDIT_FQ_ROLES = [f"{CREDIT_ROOT_URL}{role}/" for role in CREDIT_ROLES]

# See https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/contributor/#a-contributortype
DATACITE_CONTRIBUTOR_TYPES = [
    "DataCollector",
    "DataCurator",
    "DataManager",
    "Distributor",
    "Editor",
    "HostingInstitution",
    "Producer",
    "ProjectLeader",
    "ProjectManager",
    "ProjectMember",
    "RegistrationAgency",
    "RegistrationAuthority",
    "RelatedPerson",
    "Researcher",
    "ResearchGroup",
    "RightsHolder",
    "Sponsor",
    "Supervisor",
    "Translator",
    "WorkPackageLeader",
    "Other",
]

DATACITE_FMT_TYPES = [t.lower() for t in DATACITE_CONTRIBUTOR_TYPES]

DEFAULT_AUTHOR_ROLE = "associatedWith"


###############################################################################
# Helpers
###############################################################################
def _is_credit_role(role: str):
    role_fmt = role.lower().replace(" ", "-")
    if role.startswith(CREDIT_ROOT_URL):
        return role_fmt in CREDIT_FQ_ROLES
    else:
        return role_fmt in CREDIT_ROLES


def _is_datacite_contrib_type(role: str):
    return role.lower() in DATACITE_FMT_TYPES


###############################################################################
# Functions
###############################################################################

# See https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/creator/#a-nameidentifierscheme
def uri_to_identifier_schema(uri: str):
    fmt_uri = uri.lower()

    if "orcid" in fmt_uri:
        return "ORCID"
    elif "isni" in fmt_uri:
        return "ISNI"
    elif "ror" in fmt_uri:
        return "ROR"
    elif "tag" in fmt_uri:
        return "tag"
    elif "uuid" in fmt_uri:
        return "UUID"
    else:
        return None


def name_identifier_scheme_uri(scheme: NameIdentifierScheme):
    if scheme == NameIdentifierScheme.ORCID:
        return "https://orcid.org/"
    elif scheme == NameIdentifierScheme.ISNI:
        return "https://isni.org/"
    elif scheme == NameIdentifierScheme.ROR:
        return "https://ror.org/"
    elif scheme == NameIdentifierScheme.TAG:
        return "https://www.rfc-editor.org/rfc/rfc4151"
    elif scheme == NameIdentifierScheme.UUID:
        return "https://www.rfc-editor.org/rfc/rfc4122"
    else:
        return None


def check_role_in_known_taxonomy(role: str):
    if _is_credit_role(role):
        return RoleTaxonomy.CREDIT
    elif _is_datacite_contrib_type(role):
        return RoleTaxonomy.DATACITE
    else:
        return RoleTaxonomy.NONE
