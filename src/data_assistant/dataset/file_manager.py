"""FileManager module."""
from __future__ import annotations

import logging
from os import path
from typing import TYPE_CHECKING, Generic, TypeVar

from filefinder import Finder

from .cache import CacheMixin, autocached

if TYPE_CHECKING:
    from .dataset import DatasetBase

    _DB = DatasetBase
else:
    _DB = object

log = logging.getLogger(__name__)


_FileT = TypeVar("_FileT")


class MultiFilesAbstract(Generic[_FileT], _DB):
    def get_filename(self, **fixes) -> _FileT:
        raise NotImplementedError()

    def get_source(self) -> list[_FileT]:
        raise NotImplementedError()


class FileFinderMixin(MultiFilesAbstract, CacheMixin, _DB):
    """Multifiles manager using Filefinder.

    Written for datasets comprising of many datafiles, either because of the have long
    time series, or many parameters.
    The user has to define two methods. One returning the root directory containing
    all the datafiles (:meth:`get_root_directory`). And another one returning the
    filename pattern (:meth:`get_filename_pattern`). Using methods allows to return
    a different directory or pattern depending on the parameters.

    The filename pattern specify the parts of the datafiles that vary from file to file
    using a powerful syntax. See the filefinder package `documentation
    <https://filefinder.readthedocs.io/en/latest/>`_ for the details.

    The parameters that are specified in the filename pattern, and thus correspond to
    variations from file to file (the date in daily datafiles for instance) are called
    'fixables'. If they are not set, the filemanager will select all files, which is
    okay for finding files and opening the corresponding data. If the user 'fix' them to
    a value, only part of the files will be selected. Some operation require all
    parameters to be set, for instance to generate a specific filename.

    The fixable parameters are added to the dataset allowed parameters uppon
    initialization, which is important if parameters checking is enabled.
    """

    # Methods to be overwritten by user

    def get_root_directory(self) -> str | list[str]:
        """Return the directory containing all datafiles.

        Can return a path, or an iterable of directories that will automatically be
        joined.

        Define this method on the parent :class:`DatasetAbstract`.
        """
        raise NotImplementedError(
            "This method should be implemented in your Dataset class."
        )

    def get_filename_pattern(self) -> str:
        """Return the filename pattern.

        See the Filefinder documentation on the syntax:
        `https://filefinder.readthedocs.io/en/latest/find_files.html`.

        Define this method on the parent :class:`DatasetAbstract`.
        """
        raise NotImplementedError(
            "This method should be implemented in your Dataset class."
        )

    # Method overwritting DatasetBase

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Add fixable_params to the dataset allowed_params
        # self.allowed_params |= set(self.fixable)

    def get_source(self) -> list[str]:
        return self.datafiles

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
        """
        # Check they can be fixed (they exist in the pattern)
        for f in fixes:
            if f not in self.fixable:
                raise KeyError(f"Parameter {f} cannot be fixed.")

        # In case params were changed sneakily and the cache was not invalidated
        fixable_params = {
            p: value for p, value in self.params.items() if p in self.fixable
        }
        fixes = fixable_params | fixes

        # Remove parameters set to None, FileFinder is not equipped for that
        fixes = {p: value for p, value in fixes.items() if value is not None}

        filename = self.filefinder.make_filename(fixes)
        return filename

    # --

    @property
    def root_directory(self) -> str:
        """Root directory containing data."""
        rootdir = self.get_root_directory()

        if isinstance(rootdir, list | tuple):
            rootdir = path.join(*rootdir)

        return rootdir

    @property
    def filename_pattern(self) -> str:
        """Filename pattern used to find files using :mod:`filefinder`."""
        return self.get_filename_pattern()

    @property
    @autocached
    def filefinder(self) -> Finder:
        """Filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.
        """
        finder = Finder(self.root_directory, self.filename_pattern)

        # We now fix the parameters present in the filename whose value is specified
        # in the parent dataset (we don't have to worry about them after that).
        # We cache this temporary finder to avoid infinite recursion when
        # getting the names of the varying parameters.
        self.set_in_cache("filefinder", finder)
        varying = self.fixable

        for p, value in self.params.items():
            if p in varying and value is not None:
                finder.fix_group(p, value)

        # All operations above were in-place, so this is not needed but just in case, we
        # clean the cache. The @autocached will take care of caching.
        self.cache.pop("filefinder")
        return finder

    @property
    @autocached
    def fixable(self) -> list[str]:
        """List of parameters that can vary in the filename.

        Found automatically from a :class:`filefinder.Finder` instance.
        This correspond to the list of the group names in the Finder (without
        duplicates).
        """
        fixable = [g.name for g in self.filefinder.groups]
        # remove duplicates
        return list(set(fixable))

    @property
    @autocached
    def unfixed(self) -> list[str]:
        """List of varying parameters whose value is not fixed.

        Considering the current set of parameters of the dataset.
        Parameters set to ``None`` are left unfixed.
        """
        unfixed = [g.name for g in self.filefinder.groups if g.fixed_value is None]
        # remove duplicates
        return list(set(unfixed))

    @property
    @autocached
    def datafiles(self) -> list[str]:
        """Datafiles available.

        Use the :attr:`filefinder` object to scan for files corresponding to
        the filename pattern.
        """
        files = self.filefinder.get_files()
        if len(files) == 0:
            log.warning("%s", self.filefinder)
        return files
