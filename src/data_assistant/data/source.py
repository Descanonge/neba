"""Plugin to manages and find data sources.

Currently mainly give some basic options for the source being multiple files on disk.
"""
from __future__ import annotations

import logging
from os import path

from .plugin import CachePlugin, autocached

log = logging.getLogger(__name__)


class MultiFilePluginAbstract(CachePlugin):
    """Abstract class for source consisting of multiple files.

    It is easier to deal with multiple files when separating a root directory, and the
    files therein. :meth:`root_directory` deals with that.

    Also defines an autocached property :meth:`datafiles` that will be returned upon
    asking the source. If they are many files, caching this can make sense.
    """

    def get_filename(self, **fixes) -> str:
        """Create a filename corresponding to a set of parameters values.

        All parameters must be defined, either in the DataManager
        :attr:`~.data_manager.DataManagerBase.params`, or by the ``fixes``
        arguments.

        :Not implemented: implement in your DataManager subclass or a plugin subclass.

        Parameters
        ----------
        fixes:
            Parameters to fix to specific values to obtain a filename. Should take
            precedence over the parent ``params`` attribute, which will be unaffected.
        """
        raise NotImplementedError(
            "Implement in your DataManager subclass or a plugin subclass."
        )

    def get_root_directory(self) -> str | list[str]:
        """Return the directory containing all datafiles.

        Can return a path, or an iterable of directories that will automatically be
        joined into a valid path.

        :Not implemented: implement in your DataManager subclass.
        """
        raise NotImplementedError("Implemented in your DataManager subclass.")

    @property
    def root_directory(self) -> str:
        """Root directory containing data.

        Call :meth:`get_root_directory` and, if necessary, joins individuals folders
        into a single path.
        """
        rootdir = self.get_root_directory()

        if isinstance(rootdir, list | tuple):
            rootdir = path.join(*rootdir)

        return rootdir

    def get_source(self) -> list[str]:  # noqa: D102
        if len(self.datafiles) == 0:
            raise ValueError(f"No files were found '{self}'.")
        return self.datafiles

    @property
    @autocached
    def datafiles(self) -> list[str]:
        """Cached list of source files.

        :Not implemented: implement in plugin subclass.
        """
        raise NotImplementedError("Implement in plugin subclass.")


class GlobPlugin(MultiFilePluginAbstract, CachePlugin):
    """Find files using glob patterns.

    Relies on the function :func:`glob.glob`.
    Glob pattern are Unix shell-style wildcards:

    * ``*`` matches everything
    * ``?`` matches a single character
    * ``[seq]`` matches any character in seq (once)
    * ``[!seq]`` matches any character *not* in seq
    """

    RECURSIVE: bool = True
    """Correspond to the recursive argument to glob.

    If True, the pattern ``**`` will match any files and zero or more directories,
    subdirectories and symbolic links to directories.
    """

    def get_glob_pattern(self) -> str:
        """Return the glob pattern matching your files.

        If it is defined, the pattern starts from :meth:`get_root_directory`.

        :Not implemented: implement in your DataManager subclass.
        """
        raise NotImplementedError("Implement in your DataManager subclass.")

    @property
    @autocached
    def datafiles(self) -> list[str]:
        """Cached list of files found by using glob."""
        import glob

        try:
            root = self.root_directory
        except NotImplementedError:
            root = None

        pattern = self.get_glob_pattern()
        files = glob.glob(pattern, root_dir=root, recursive=self.RECURSIVE)

        if len(files) == 0:
            log.warning("No file found for pattern %s", pattern)
        return files
