"""Plugin to manages and find data sources.

Currently mainly give some basic options for the source being multiple files on disk.
"""

from __future__ import annotations

import itertools
import logging
import typing as t
from collections import abc
from os import PathLike, path

from .module import CachedModule, Module, ModuleMix, autocached
from .util import T_Source

log = logging.getLogger(__name__)

if t.TYPE_CHECKING:
    from filefinder import Finder

T_MultiSource = t.TypeVar("T_MultiSource", bound=abc.Sequence)


class SourceAbstract(t.Generic[T_Source], Module):
    """Abstract of source managing module."""

    def get_source(self, _warn: bool = True) -> T_Source:
        """Return source of data.

        :Not Implemented: Implement in Module subclass
        """
        raise NotImplementedError("Implement in Module subclass.")


class SimpleSource(SourceAbstract[T_Source]):
    """Simple module where data source is specified by class attribute.

    The source is specified in :attr:`source_loc`.
    """

    source_loc: T_Source
    """Location of the source to return."""

    def get_source(self, _warn: bool = True) -> T_Source:
        """Return source specified by :attr:`source_loc` attribute."""
        return self.source_loc

    def _lines(self) -> list[str]:
        return [f"Source directly specified: {self.get_source()}"]


class MultiFileSource(SourceAbstract[list[str]]):
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

    def get_source(self, _warn: bool = True) -> list[str]:  # noqa: D102
        datafiles = self.datafiles
        if _warn and len(datafiles) == 0:
            log.warning("No files found for %s", repr(self))
        return self.datafiles

    @property
    def datafiles(self) -> list[str]:
        """Cached list of source files.

        :Not implemented: implement in plugin subclass.
        """
        raise NotImplementedError("Implement in plugin subclass.")


class GlobSource(MultiFileSource, CachedModule):
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
        return files

    def _lines(self) -> list[str]:
        """Human readable description."""
        lines = super()._lines()
        lines += [
            f"Glob pattern '{self.get_glob_pattern()}'",
            f"In root directory '{self.root_directory}'",
        ]
        return lines


class FileFinderSource(MultiFileSource, CachedModule):
    """Multifiles manager using Filefinder.

    Written for datasets comprising of many datafiles, either because of they have long
    time series, or many parameters.
    The user has to define two methods. One returning the root directory containing
    all the datafiles (:meth:`get_root_directory`). And another one returning the
    filename pattern (:meth:`get_filename_pattern`). Using methods allows to return
    a different directory or pattern depending on the parameters.

    .. note::

        It is important to note that only parameters in the filename pattern can take
        multiple values in a single :meth:`~.data_manager.DataManagerBase.get_source`
        call. To get files from different root directories and merge the results,
        the current solution is to use :meth:`~.data_manager.DataManager.get_data_sets`.

    The filename pattern specify the parts of the datafiles that vary from file to file
    using a powerful syntax. See the filefinder package `documentation
    <https://filefinder.readthedocs.io/en/latest/>`_ for the details.

    The parameters that are specified in the filename pattern, and thus correspond to
    variations from file to file (the date in daily datafiles for instance) are called
    'fixables'. If they are not set, the filemanager will select all files, which is
    okay for finding files and opening the corresponding data. If the user 'fix' them to
    parameters to be set, for instance to generate a specific filename.
    a value, only part of the files will be selected. Some operation require all
    """

    def get_filename_pattern(self) -> str:
        """Return the filename pattern.

        The filename pattern specify the parts of the datafiles that vary from file to
        file. See the filefinder package `documentation
        <https://filefinder.readthedocs.io/en/latest/>`_ for the details.

        :Not implemented: implement in your DataManager class.
        """
        raise NotImplementedError("Implement in your DataManager class.")

    def get_filename(self, relative: bool = False, **fixes) -> str:
        """Create a filename corresponding to a set of parameters values.

        All parameters must be defined, either by the parent
        :attr:`DatasetAbstract.params`, or by the ``fixes`` arguments.

        Parameters
        ----------
        relative:
            If True, make the file relative to the root directory. Default is False.
        fixes:
            Parameters to fix to specific values. Only parameters defined in the
            filename pattern can be fixed. Will take precedence over the
            parent ``params`` attribute.
        """
        # Check they can be fixed (they exist in the pattern)
        for f in fixes:
            if f not in self.fixable:
                raise KeyError(f"Parameter {f} cannot be fixed '{self}'.")

        # In case params were changed sneakily and the cache was not invalidated
        fixable_params = {
            p: self.dm.params[p] for p in self.fixable if p in self.dm.params
        }
        fixes = fixable_params | fixes

        # Remove parameters set to None, FileFinder is not equipped for that
        fixes = {p: value for p, value in fixes.items() if value is not None}

        filename = self.filefinder.make_filename(fixes, relative=relative)
        return filename

    @property
    @autocached
    def filefinder(self) -> Finder:
        """Filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.
        """
        from filefinder import Finder

        finder = Finder(self.root_directory, self.get_filename_pattern())

        # We now fix the parameters present in the filename (we don't have to worry
        # about them after that). We re-use code from self.fixable to avoid
        # infinite recursion
        fixable = finder.get_group_names()

        for p in fixable:
            if (value := self.dm.params.get(p, None)) is not None:
                finder.fix_group(p, value)
        return finder

    @property
    @autocached
    def fixable(self) -> list[str]:
        """List of parameters that can vary in the filename.

        Found automatically from a :class:`filefinder.Finder` instance.
        This correspond to the list of the group names in the Finder (without
        duplicates).
        """
        return list(self.filefinder.get_group_names())

    @property
    @autocached
    def unfixed(self) -> list[str]:
        """List of varying parameters whose value is not fixed.

        Considering the current set of parameters of the dataset.
        Parameters set to ``None`` or set to a sequence of values are considered
        unfixed.
        """
        unfixed = [
            g.name
            for g in self.filefinder.groups
            if g.fixed_value is None or isinstance(g.fixed_value, abc.Sequence)
        ]
        # remove duplicates
        return list(set(unfixed))

    @property
    @autocached
    def datafiles(self) -> list[str]:
        """Datafiles available.

        Use the :attr:`filefinder` object to scan for files corresponding to
        the filename pattern.
        """
        return self.filefinder.get_files()

    def _lines(self) -> list[str]:
        """Human readable description."""
        s = [f"FileFinder pattern '{self.get_filename_pattern()}'"]
        if "filefinder" in self.cache:
            fixes = {}
            for grp in self.filefinder.groups:
                if grp.fixed:
                    fixes[grp.name] = grp.fixed_value
            if fixes:
                s.append(
                    "\twith fixed values: "
                    + ", ".join([f"{name}: {value}" for name, value in fixes.items()])
                )
        s.append(f"In root directory '{self.root_directory}'")
        if "datafiles" in self.cache:
            s.append(f"Found {len(self.datafiles)} files")
        return s


# maybe try better way to deal with this since now we can modify the source module
# at runtime with an eventual parameter 'climato=something' ?


class climato:  # noqa: N801
    """Create a Dataset subclass for climatology.

    Generate new subclass of a source module that correspond to its climatology.
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

    def __call__(self, cls: type[FileFinderSource]):
        """Apply decorator."""
        from filefinder import Finder

        time_pattern_names = "SXMHjdxFmBY"

        def get_root_dir_wrapped(obj):
            root_dir = super(cls, obj).get_root_directory()
            if isinstance(root_dir, str | PathLike):
                root_dir = path.join(root_dir, self.append_folder)
            else:
                root_dir.append(self.append_folder)
            return root_dir

        # Change get_filename_pattern
        def get_filename_pattern_wrapped(obj):
            pattern = super(cls, obj).get_filename_pattern()
            finder = Finder("", pattern)
            for g in finder.groups:
                # remove fixable/groups related to time
                if g.name in time_pattern_names:
                    pattern = pattern.replace(f"%({g.definition})", "")

            infile, ext = path.splitext(pattern)
            # Clean pattern
            infile = infile.strip("/_-")
            # Add climatology group
            infile += r"_%(climatology:fmt=s:rgx=\s+)"

            pattern = infile + ext
            return pattern

        changes: dict[str, t.Any] = {}
        changes["get_filename_pattern"] = get_filename_pattern_wrapped
        if self.append_folder:
            changes["get_root_directory"] = get_root_dir_wrapped

        newcls = type(f"{cls.__name__}Climatology", (cls,), changes)

        return newcls


T_ModSource = t.TypeVar("T_ModSource", bound=SourceAbstract)


class _SourceMix(SourceAbstract, ModuleMix[T_ModSource]):
    def get_filename(
        self, all: bool = False, select: dict[str, t.Any] | None = None, **fixes
    ) -> T_ModSource | list[T_ModSource]:
        return self.get("get_filename", all, select=select, **fixes)

    def _get_grouped_source(self) -> list[list[t.Any]]:
        grouped = self.get_all("get_source", _warn=False)
        # I expect grouped to be list[list[Any] | Any]
        # we make sure we only have lists: list[list[Any]]
        source = []
        for grp in grouped:
            if not isinstance(grp, list | tuple):
                grp = [grp]
            source.append(grp)
        return source

    def check_valid(self, source: abc.Sequence[t.Any]) -> bool:  # noqa: D102
        """Check if source is valid.

        Assume a mix of source results in multiple items. We check there is at least
        one.
        """
        return len(source) > 0


class SourceUnion(_SourceMix[T_ModSource]):
    """Sources are the union of that obtained by multiple modules.

    Pass the different source modules to "combine" to
    :meth:`SourceUnion.create()<.ModuleMix.create>` which will return a new module
    class. As so::

        MyUnion = SourceUnion.create([Source1, Source2])

    The union module will output all the files found by any of the initial modules,
    without duplicates, in the order of how the modules were given to ``create``.
    """

    def _lines(self) -> list[str]:
        s = super()._lines()
        s.insert(0, "Union of sources from modules:")
        return s

    def get_source(self, _warn: bool = True) -> list[t.Any]:
        source = self._get_grouped_source()
        # use fromkeys to remove duplicates. dict keep order which is nice
        union = list(dict.fromkeys(itertools.chain(*source)))
        if _warn:
            if len(union) == 0:
                log.warning("No files found for %s", repr(self))
        return union


class SourceIntersection(_SourceMix[T_ModSource]):
    """Sources are the intersection of that obtained by multiple modules.

    Pass the different source modules to "combine" to
    :meth:`SourceIntersection.create()<.ModuleMix.create>` which will return a new
    module class. As so::

        MyIntersection = SourceIntersection.create([Source1, Source2])

    The intersection module will only output the files found by all of the initial
    modules.
    """

    def _lines(self) -> list[str]:
        s = super()._lines()
        s.insert(0, "Intersection of sources from modules:")
        return s

    def get_source(self, _warn: bool = True) -> list[t.Any]:
        groups = self._get_grouped_source()
        inter: set[t.Any] = set().intersection(*[set(g) for g in groups])
        if _warn:
            if len(inter) == 0:
                log.warning("No files found for %s", repr(self))
        return list(inter)
