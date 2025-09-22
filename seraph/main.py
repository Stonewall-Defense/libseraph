###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from .exec.audio import audio
from .exec.classes import classes
from .exec.integrations import integrations
from .exec.meta import meta
from .exec.provenance import prov
from .exec.prune import prune
from .exec.splits import splits
from .exec.version import version


###############################################################################
# Commands
###############################################################################
@click.group()
def cli():
    pass


cli.add_command(audio)
cli.add_command(classes)
cli.add_command(integrations)
cli.add_command(meta)
cli.add_command(prov)
cli.add_command(prune)
cli.add_command(splits)
cli.add_command(version)


###############################################################################
# ! MAIN
###############################################################################
if __name__ == "__main__":
    cli()
