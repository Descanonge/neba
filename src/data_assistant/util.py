import logging
import os
from os import path

logger = logging.getLogger(__name__)


def check_output_path(
    outpath: str, directory: bool = False, log: bool | str | int = True
):
    """Check if directory exists, if not create it.

    Parameters
    ----------
    outpath:
        Output file or directory.
    directory:
        If True, `outpath` is a directory, if False (the default) `outpath` is a
        file and we will check the existence of its containing directory.
    log:
        If True, will log output file. If string or integer, specify the
        level of message (default is DEBUG).
    """
    # Find directory to check existence of
    if directory:
        outdir = outpath
    else:
        outdir = path.dirname(outpath)

    # Set log level
    if log is True:
        log = logging.DEBUG
    if isinstance(log, str):
        log = logging.getLevelNamesMapping()[log.upper()]

    if log:
        logger.log(log, 'output to %s', outdir if directory else outpath)

    # Check if directory exists
    if not path.isdir(outdir):
        if log:
            logger.log(log, 'creating %s', outdir)
        os.makedirs(outdir)
