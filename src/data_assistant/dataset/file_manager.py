"""FileManager module."""
from __future__ import annotations

import logging
from os import PathLike, path
from typing import Generic, TypeVar

from filefinder import Finder

from .dataset import Module
from .module import CacheModule, autocached

log = logging.getLogger(__name__)


_FileT = TypeVar("_FileT")


class MultiFileModuleAbstract(Generic[_FileT], Module):
    def get_filename(self, **fixes) -> _FileT:
        raise NotImplementedError()

    def get_source(self) -> list[_FileT]:
        raise NotImplementedError()


class FileFinderModule(MultiFileModuleAbstract, CacheModule):
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

    def _init_module(self) -> None:
        super()._init_module()

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


class climato:  # noqa: N801
    """Create a Dataset subclass for climatology.

    Generate new subclass of a dataset that correspond to its climatology.
    Have to wrap around base class get_root and get_pattern.
    Pattern is not easy, we have to get rid of time related groups.

    Parameters
    ----------
    append_folder:
        If None, do not change the root directory. If is a string, append it as a
        new directory.
    """

    def __init__(self, append_folder: str | None = None):
        self.append_folder = append_folder

    def __call__(self, cls: FileFinderModule):
        """Apply decorator."""
        from filefinder import Finder
        from filefinder.group import TIME_GROUPS

        # Change get_root_directory
        if self.append_folder:

            def get_root_dir_wrapped(obj):
                root_dir = super(cls, obj).get_root_directory()
                if isinstance(root_dir, str | PathLike):
                    root_dir = path.join(root_dir, self.append_folder)
                else:
                    root_dir.append(self.append_folder)
                return root_dir

            cls.get_root_directory = get_root_dir_wrapped  # type: ignore

        # Change get_filename_pattern
        def get_filename_pattern_wrapped(obj):
            pattern = super(cls, obj).get_filename_pattern()
            finder = Finder("", pattern)
            for g in finder.groups:
                # remove fixable/groups related to time
                if g.name in TIME_GROUPS:
                    pattern = pattern.replace(f"%({g.definition})", "")

            infile, ext = path.splitext(pattern)
            # Clean pattern
            infile = infile.strip("/_-")
            # Add climatology group
            infile += r"_%(climatology:fmt=s:rgx=\s+)"

            pattern = infile + ext
            return pattern

        cls.get_filename_pattern = get_filename_pattern_wrapped  # type: ignore

        if cls.ID:
            cls.ID = f"{cls.ID}_cli"
        if cls.SHORTNAME:
            cls.SHORTNAME = f"{cls.SHORTNAME}_cli"

        return cls
