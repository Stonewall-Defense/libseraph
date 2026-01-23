###############################################################################
# Global Imports
###############################################################################
from dataclasses import dataclass
from enum import Enum
import os
import pathlib
import sqlite3
from typing import Optional

###############################################################################
# Local Imports
###############################################################################
from .common import SERAPH_INTERNAL_DIR, now_str, str_to_enum


###############################################################################
# Enums
###############################################################################
class VersionBumpType(Enum):
    N_A = "n/a"     # Not used
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


class ChangeType(Enum):
    ADD = "add"
    CHANGE = "change"
    REMOVE = "remove"


###############################################################################
# Data Classes
###############################################################################
@dataclass
class ImportRecord:
    uri: str
    version: str
    name: str
    classes: Optional[list[str]] = None


@dataclass(kw_only=True)
class ChangeRecord:
    bump_type: VersionBumpType
    change_type: ChangeType
    message: str
    is_import: bool = False


@dataclass
class VersionRecord:
    version: str
    datetime: str
    prov_was_submitted: bool
    imports: list[ImportRecord]
    changes: list[ChangeRecord]


###############################################################################
# Constants
###############################################################################
CHANGE_RECORD_FILENAME = "change_record.db"


###############################################################################
# Helpers
###############################################################################
def import_rec_factory(cur: sqlite3.Cursor, row: sqlite3.Row) -> ImportRecord:
    classes = row[3].split(";") if row[3] else None

    return ImportRecord(
        uri=row[0],
        version=row[1],
        name=row[2],
        classes=classes,
    )


def change_rec_factory(cur: sqlite3.Cursor, row: sqlite3.Row) -> ChangeRecord:
    return ChangeRecord(
        bump_type=str_to_enum(row[0], VersionBumpType),
        change_type=str_to_enum(row[1], ChangeType),
        message=row[2],
        is_import=int(row[3]) == 1,
    )


def version_rec_factory(cur: sqlite3.Cursor, row: sqlite3.Row) -> VersionRecord:
    return VersionRecord(
        version=row[0],
        datetime=row[1],
        prov_was_submitted=int(row[2]) == 1,
        imports=[],
        changes=[],
    )


###############################################################################
# Classes
###############################################################################
class HistoryManager:
    def __init__(self, dir: str):
        self.fq_internal_dirname, self.fq_change_filename = HistoryManager.initialize(dir)

        # Dataset governance
        self.change_records: list[ChangeRecord] = []
        self.import_records: list[ImportRecord] = []

    ###########################################################################
    # Write
    ###########################################################################
    def register_change(self, change: Optional[ChangeRecord]):
        if change:
            self.change_records.append(change)

    def register_import(self, import_rec: Optional[ImportRecord]):
        if import_rec:
            self.import_records.append(import_rec)

    def register_changes(self, changes: list[ChangeRecord]):
        self.change_records += changes

    def register_imports(self, import_recs: list[ImportRecord]):
        self.import_records += import_recs

    def register(self,
                 *,
                 change: Optional[ChangeRecord] = None,
                 import_rec: Optional[ImportRecord] = None,
                 ):
        self.register_change(change)
        self.register_import(import_rec)

    def register_all(self,
                     *,
                     changes: list[ChangeRecord] = [],
                     import_recs: list[ImportRecord] = [],
                     ):
        self.register_changes(changes)
        self.register_imports(import_recs)

    def save(self, current_version: str):
        self._save_change_records(current_version)
        self._save_import_records(current_version)

    def update_version(self, next_version: str):
        con = sqlite3.connect(self.fq_change_filename)

        with con:
            query = "INSERT INTO versions VALUES ( ?, ?, ? )"
            con.execute(query, [next_version, now_str(), False])
        con.close()

    def mark_prov_submission(self, version: Optional[str] = None):
        con = sqlite3.connect(self.fq_change_filename)

        with con:
            if not version:
                cur = con.execute("SELECT version FROM versions ORDER BY datetime DESC limit 1")
                version = cur.fetchone()[0]
            query = "UPDATE versions SET prov_submitted = TRUE WHERE version = ?"
            con.execute(query, [version])
        con.close()

    ###########################################################################
    # Read
    ###########################################################################
    def load_changes(self, version: Optional[str]) -> tuple[list[ImportRecord], list[ChangeRecord]]:
        con = sqlite3.connect(self.fq_change_filename)

        with con:
            cur = con.cursor()
            version = version or self._get_latest_version(cur)
            return self._load_changes_for_version(version, cur)

    def load_change_list(self, versions: Optional[list[str]]):
        con = sqlite3.connect(self.fq_change_filename)
        with con:
            cur = con.cursor()

            # Get version list
            cur.row_factory = version_rec_factory
            if versions:
                cur.execute("SELECT version, datetime, prov_submitted FROM versions WHERE version IN ( ? ) AND version != '0.0.0' ORDER BY datetime DESC", [versions])
            else:
                cur.execute("SELECT version, datetime, prov_submitted FROM versions WHERE version != '0.0.0' ORDER BY datetime DESC")
            versions_fmt: list[VersionRecord] = cur.fetchall()

            for v in versions_fmt:
                v.imports, v.changes = self._load_changes_for_version(v.version, cur)

            return versions_fmt

    def check_prov_submission(self, version: Optional[str] = None):
        con = sqlite3.connect(self.fq_change_filename)

        submitted = False

        with con:
            cur = con.cursor()
            version = version or self._get_latest_version(cur)

            query = "SELECT prov_submitted FROM versions WHERE version = ?"
            cur = con.execute(query, [version])
            val = cur.fetchone()
            submitted = int(val[0]) == 1
        con.close()

        return submitted

    def load_sources(self) -> list[ImportRecord]:
        con = sqlite3.connect(self.fq_change_filename)
        with con:
            cur = con.cursor()
            cur.row_factory = import_rec_factory
            cur.execute("SELECT import_uri, import_version, import_name, import_classes FROM components")
            imports: list[ImportRecord] = cur.fetchall()
            return imports

    ###########################################################################
    # Internal Writers
    ###########################################################################
    def _save_change_records(self, current_version: str):
        if not self.change_records:
            return

        data = [
            (current_version, c.bump_type.value, c.change_type.value, c.message, c.is_import) for c in self.change_records
        ]
        query = "INSERT INTO modifications VALUES ( ?, ?, ?, ?, ? )"

        con = sqlite3.connect(self.fq_change_filename)

        with con:
            con.executemany(query, data)
        con.close()

        self.change_records = []

    def _save_import_records(self, current_version: str):
        if not self.import_records:
            return

        data = [
            (current_version, i.uri, i.version, i.name, ";".join(i.classes) if i.classes else None) for i in self.import_records
        ]
        query = "INSERT INTO components ( current_version, import_uri, import_version, import_name, import_classes ) VALUES ( ?, ?, ?, ?, ? )"

        con = sqlite3.connect(self.fq_change_filename)

        with con:
            con.executemany(query, data)
        con.close()

        self.change_records = []

    ###########################################################################
    # Internal Readers
    ###########################################################################
    def _get_latest_version(self, cur: sqlite3.Cursor):
        cur = cur.execute("SELECT version FROM versions ORDER BY datetime DESC limit 1")
        version: str = cur.fetchone()[0]
        return version

    def _load_changes_for_version(self, version: str, cur: sqlite3.Cursor):
        # Imports
        cur.row_factory = import_rec_factory
        cur.execute("SELECT import_uri, import_version, import_name, import_classes FROM components WHERE current_version = ?", [version])
        imports: list[ImportRecord] = cur.fetchall()

        # Changes
        cur.row_factory = change_rec_factory
        cur.execute("SELECT bump_type, change_type, message, is_import FROM modifications WHERE current_version = ?", [version])
        changes: list[ChangeRecord] = cur.fetchall()

        return imports, changes

    ###########################################################################
    # Static Helpers
    ###########################################################################
    @staticmethod
    def initialize(dir: str):
        fq_internal_dirname = os.path.join(dir, SERAPH_INTERNAL_DIR)
        pathlib.Path(fq_internal_dirname).mkdir(parents=True, exist_ok=True)

        fq_change_filename = os.path.join(fq_internal_dirname, CHANGE_RECORD_FILENAME)
        con = sqlite3.connect(fq_change_filename)

        with con:
            con.execute("CREATE TABLE IF NOT EXISTS components ( current_version, import_uri, import_version, import_name, import_classes )")
            con.execute("CREATE TABLE IF NOT EXISTS modifications ( current_version, bump_type, change_type, message, is_import )")
            con.execute("CREATE TABLE IF NOT EXISTS versions ( version, datetime, prov_submitted )")

            cur = con.execute("SELECT * FROM versions LIMIT 1")
            if cur.fetchone() is None:
                cur.execute("INSERT INTO versions VALUES ( ?, ?, ? )", ["0.0.0", now_str(), True])

        con.close()

        return fq_internal_dirname, fq_change_filename
