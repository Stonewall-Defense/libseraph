###############################################################################
# Global Imports
###############################################################################
import json
import re
import warnings

###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from ..lib import SeraphDataset, write_json


###############################################################################
# Constants
###############################################################################
CLASS_NAME_REPLACE_PATTERN = re.compile(r'[^\w\s]')


###############################################################################
# ! Commands
###############################################################################
@click.group("integrations")
def integrations():
    pass


@integrations.group("fuelai")
def fuelai():
    pass


@fuelai.command("export")
@click.option("--dataset_path", default=".")
@click.option("--force", is_flag=True)
def fuelai_export(dataset_path: str, force: bool):
    dataset = SeraphDataset(dataset_path)
    classes = dataset.get_classes()

    mod_classes = [c for c in classes if re.search(CLASS_NAME_REPLACE_PATTERN, c) is not None]
    if mod_classes:
        mod_str = f"Classes {', '.join(mod_classes)} {'will' if force else 'would'} be modified during the export process"
        if force:
            warnings.warn(mod_str)
        else:
            raise ValueError(mod_str)

    fuelai_classes = [{"name": re.sub(CLASS_NAME_REPLACE_PATTERN, "_", c)} for c in classes]
    write_json("fuelai-classes.json", fuelai_classes)


###############################################################################
# ! Main
###############################################################################
if __name__ == "__main__":
    integrations()
