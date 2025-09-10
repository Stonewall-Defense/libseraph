###############################################################################
# Global Imports
###############################################################################
from copy import deepcopy
from dataclasses import dataclass, asdict
import os
import pathlib
from typing import Any, Optional
import warnings


###############################################################################
# Local Imports
###############################################################################
from .common import ALLOWED_METADATA_FILENAMES, CLASSFILE_NAME, DATA_DIR, SERAPH_FILENAME
from .common import get_metadata_filename, read_csv, write_csv, read_json, write_json
from .history import HistoryManager, ChangeRecord, ImportRecord


###############################################################################
# Data Classes
###############################################################################
@dataclass
class DatasetAuthor:
    uri: str
    rel: str


@dataclass
class SeraphMetadata:
    uri: str
    name: str
    version: str
    author: Optional[DatasetAuthor]
    keywords: list[str]
    mediaType: Optional[str]
    mediaSubtype: Optional[str]
    license: Optional[str]

    # mediaMetadata -> [mediaType] -> [mediaSubtype] -> key:value
    mediaMetadata: Optional[dict[str, dict[str, Any]]]


###############################################################################
# Errors
###############################################################################
class SeraphMetadataError(Exception):
    pass


###############################################################################
# Helpers
###############################################################################
def _load_seraph_file(fq_filename: str) -> SeraphMetadata:
    seraph = read_json(fq_filename)

    if seraph.get("author", None):
        author = DatasetAuthor(
            uri=seraph["author"]["uri"],
            rel=seraph["author"]["rel"],
        )
    else:
        author = None

    media_type = seraph.get("mediaType", None)
    if media_type and "/" in media_type:
        media_type, media_subtype = media_type.split("/")
    else:
        media_subtype = seraph.get("mediaSubtype", None)

    return SeraphMetadata(
        uri=seraph["uri"],
        name=seraph["name"],
        version=seraph["version"],
        author=author,
        keywords=seraph.get("keywords", []),
        mediaType=media_type,
        mediaSubtype=media_subtype,
        license=seraph.get("license", None),
        mediaMetadata=seraph.get("mediaMetadata", None),
    )


###############################################################################
# Classes
###############################################################################
class SeraphDataset:
    def __init__(self, dir: str) -> None:
        # Directory stuff
        self.dir = dir
        self.fq_data_dir, self.history_manager = SeraphDataset.ensure_internal_dirs_exist(dir)

        # Sanity check
        SeraphDataset.directory_is_seraph_dataset(dir)

        # Metadata
        self.metadata_filename = get_metadata_filename(dir)
        self.fq_metadata_filename = os.path.join(self.dir, self.metadata_filename)
        self.fieldnames, self.metadata = read_csv(self.fq_metadata_filename)
        self.metadata_was_updated = False

        # Seraph
        self.fq_seraph_filename = os.path.join(self.dir, SERAPH_FILENAME)
        self.seraph_metadata = _load_seraph_file(self.fq_seraph_filename)
        self.seraph_was_updated = False

        # Classes
        self.fq_class_filename = os.path.join(self.dir, CLASSFILE_NAME)
        self.classes: list[str] = read_json(self.fq_class_filename)
        self.classes_were_updated = False

    ###########################################################################
    # Getters
    ###########################################################################

    def get_dataset_root_dir(self):
        return self.dir

    def get_metadata(self):
        return deepcopy(self.fieldnames), deepcopy(self.metadata)

    def get_seraph_metadata(self):
        return deepcopy(self.seraph_metadata)

    def get_classes(self):
        return deepcopy(self.classes)

    def get_data_dir(self):
        return self.fq_data_dir

    def get_history(self):
        return self.history_manager

    ###########################################################################
    # Setters
    ###########################################################################

    def set_metadata_headers(self,
                             fieldnames: list[str],
                             *,
                             change_record: Optional[ChangeRecord] = None,
                             import_record: Optional[ImportRecord] = None,
                             ):
        self.fieldnames = fieldnames
        self.metadata_was_updated = True

        self.history_manager.register(change=change_record, import_rec=import_record)

        return self

    def set_metadata_records(self,
                             records: list[dict],
                             *,
                             change_record: Optional[ChangeRecord] = None,
                             import_record: Optional[ImportRecord] = None,
                             ):
        self.metadata = records
        self.metadata_was_updated = True

        self.history_manager.register(change=change_record, import_rec=import_record)

        return self

    def set_seraph_metadata(self,
                            seraph_metadata: SeraphMetadata,
                            *,
                            change_record: Optional[ChangeRecord] = None,
                            import_record: Optional[ImportRecord] = None,
                            ):
        self.seraph_metadata = seraph_metadata
        self.seraph_was_updated = True

        self.history_manager.register(change=change_record, import_rec=import_record)

        return self

    def set_classes(self,
                    classes: list[str],
                    *,
                    change_record: Optional[ChangeRecord] = None,
                    import_record: Optional[ImportRecord] = None,
                    ):
        self.classes = classes
        self.classes_were_updated = True

        self.history_manager.register(change=change_record, import_rec=import_record)

        return self

    def set_multiple(self,
                     *,
                     metadata_headers: Optional[list[str]] = None,
                     metadata_records: Optional[list[dict]] = None,
                     seraph_metadata: Optional[SeraphMetadata] = None,
                     classes: Optional[list[str]] = None,
                     change_records: list[ChangeRecord] = [],
                     import_records: list[ImportRecord] = [],
                     ):
        have_updates = False

        if metadata_headers:
            self.set_metadata_headers(metadata_headers)
            have_updates = True

        if metadata_records:
            self.set_metadata_records(metadata_records)
            have_updates = True

        if seraph_metadata:
            self.set_seraph_metadata(seraph_metadata)
            have_updates = True

        if classes:
            self.set_classes(classes)
            have_updates = True

        if have_updates:
            self.history_manager.register_all(changes=change_records, import_recs=import_records)
        elif change_records or import_records:
            warnings.warn("Change/import records were submitted with no updates; ignoring.")

        return self

    def register_patch_update(self, change_record: ChangeRecord):
        self.history_manager.register_change(change_record)
        return self

    ###########################################################################
    # Utility Functions
    ###########################################################################

    def save(self):
        if self.metadata_was_updated:
            write_csv(self.fq_metadata_filename, self.fieldnames, self.metadata)

        if self.seraph_was_updated:
            seraph_file_data = asdict(self.seraph_metadata)
            write_json(self.fq_seraph_filename, seraph_file_data)

        if self.classes_were_updated:
            write_json(self.fq_class_filename, self.classes)

        self.history_manager.save(self.seraph_metadata.version)

    ###########################################################################
    # Static Helpers
    ###########################################################################
    @staticmethod
    def directory_is_seraph_dataset(dir: str):
        is_dir = os.path.isdir(dir)
        if not is_dir:
            raise ValueError(f"Input dir is not an existing directory: {dir}")

        seraph_file_path = os.path.join(dir, SERAPH_FILENAME)
        has_seraph_file = os.path.isfile(seraph_file_path)
        if not has_seraph_file:
            raise ValueError("Input dir is not a Seraph dataset: no `seraph.json` file")

        classes_file_path = os.path.join(dir, CLASSFILE_NAME)
        has_classes_file = os.path.isfile(classes_file_path)
        if not has_classes_file:
            raise ValueError("Input dir is not a Seraph dataset: no `classes.json` file")

        metadata_file_paths = [os.path.join(dir, f) for f in ALLOWED_METADATA_FILENAMES]
        has_metadata_file = any([os.path.isfile(meta) for meta in metadata_file_paths])
        if not has_metadata_file:
            raise ValueError("Input dir is not a Seraph dataset: no metadata CSV file")

        data_dir_path = os.path.join(dir, DATA_DIR)
        has_data_dir = os.path.isdir(data_dir_path)
        if not has_data_dir:
            raise ValueError("Input dir is not a Seraph dataset: no `data/` directory")

    @staticmethod
    def ensure_internal_dirs_exist(dataset_path: str):
        # Ensure data dir exists
        fq_data_dirname = os.path.join(dataset_path, DATA_DIR)
        pathlib.Path(fq_data_dirname).mkdir(parents=True, exist_ok=True)

        return fq_data_dirname, HistoryManager(dataset_path)
