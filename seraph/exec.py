###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from .audio import audio
from .classes import classes
from .init import init
from .provenance import prov
from .prune import prune
from .splits import splits
from .version import version


###############################################################################
# Commands
###############################################################################
@click.group()
def cli():
    pass


cli.add_command(audio)
cli.add_command(classes)
cli.add_command(init)
cli.add_command(prov)
cli.add_command(prune)
cli.add_command(splits)
cli.add_command(version)


###############################################################################
# ! MAIN
###############################################################################
if __name__ == "__main__":
    cli()
