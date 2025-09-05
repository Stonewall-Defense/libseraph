###############################################################################
# 3PP Imports
###############################################################################
import click

###############################################################################
# Local Imports
###############################################################################
from seraph.audio import audio
from seraph.classes import classes
from seraph.init import init
from seraph.provenance import prov
from seraph.prune import prune
from seraph.splits import splits
from seraph.version import version


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
