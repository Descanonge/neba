"""Source Plugin: manages/find sources.

Currently mainly deals with the source being multiple files on disk.
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

        All parameters must be defined, either by the parent
        :attr:`DatasetAbstract.params`, or by the ``fixes`` arguments.

        Parameters
        ----------
        fixes:
            Parameters to fix to specific values. Only parameters defined in the
            filename pattern can be fixed. Will take precedence over the
            parent ``params`` attribute.


        *Not implemented: implement in a plugin subclass or DataManager subclass.*
        """
        raise NotImplementedError()

    def get_root_directory(self) -> str | list[str]:
        """Return the directory containing all datafiles.

        Can return a path, or an iterable of directories that will automatically be
        joined into a valid path.

        *Not implemented: implement in your DataManager subclass.*
        """
        raise NotImplementedError(
            "This method should be implemented in your DataManager class."
        )

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
        return self.datafiles

    @property
    @autocached
    def datafiles(self) -> list[str]:
        """Cached list of source files.

        *Not implemented: implement in plugin subclass.*
        """
        raise NotImplementedError("Implement in plugin subclass.")


class GlobPlugin(MultiFilePluginAbstract, CachePlugin):
    """Find files using glob patterns.

    Glob pattern are Unix shell-style wildcards:

    * "*" matches everything
    * "?" matches a single character
    * [seq] matches any character in seq (once)
    * [!seq] matches any character *not* in seq
    """

    RECURSIVE: bool = True
    """Correspond to the recursive argument to glob.

    If True, the pattern "**" will any files and zero or more directories,
    subdirectories and symbolic links to directories.
    """

    def get_glob_pattern(self):
        """Return the glob pattern matching your files.

        If it is defined, the pattern starts from :meth:`get_root_directory`.

        *Not implemented: implement in your DataManager subclass.*
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
