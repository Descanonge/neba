"""Dataset objects.

The Dataset object is the main entry point for the user. By subclassing it,
they can adapt it to their data quickly.

If we want to retain the ability to define a new dataset just by subclassing
the main class, this makes splitting features into different classes challenging.
I still tried to use composition and delegate some work by "modules": FileManager,
Loader, and Writer. These retain a reference to the Dataset and can invoke
attributes and methods from it, which can be user-defined in a subclass.

I tried to stay agnostic to how a module may work to possibly accomodate for different
data formats, sources, etc. A minimal API is written in each abstract class.
It may still be quite geared towards multifiles-netcdf, since this is what I had in mind
when writing it. But hopefully it should be easy to swap modules without breaking
everything.

The parameters management is kept in the Dataset object for simplicity, maybe it
could be done by a module of its own, if this is necessary.

Modules all inherit from :class:`module.Module`, which features a caching system, with
even some attribute that can generate a new value on the fly in case of a cache
miss (see AutoCachedProperty). This was done to avoid numerous computations when
dealing with multi-files scanners.
The Dataset can trigger a flush of all caches.
"""

from collections.abc import Hashable, Iterable, Mapping, Sequence
from os import PathLike, path
from typing import Any

from filefinder import Finder
from filefinder.group import TIME_GROUPS

from data_assistant.config import Scheme

from .file_manager import FileFinderManager, FileManagerAbstract
from .loader import LoaderAbstract, XarrayLoader
from .writer import WriterAbstract, XarrayWriter


class DatasetAbstract:
    """Abstract class for a Dataset.

    This class defines the minimal dataset API, especially when communicating with
    the modules.
    It must be subclassed by the user, choosing appropriate module classes.

    * The FileManager module deals with managing the location of the datafiles.
      It is tasked to return the filename·s for a set of parameters. It could also
      deal with more general URI or data stores.
    * The Loader module loads the data into Python. Typically, the dataset provides the
      source·s obtained by the FileManager.
    * The Writer module write data to file. The Dataset can provide an output
      destination. But variations can handle complicated cases and split the data into
      multiple files by communicating directly with the FileManager.

    Each **subclass** can represent a dataset: where are the files, how to access the
    data, how to write it, etc. This dataset can depend on any number of *parameters*.
    Each **instance** of this subclass is expected to correspond to a set of (some) of
    those parameters. With those parameters the user can now access the data.

    Parameters
    ----------
    params
        Mapping of the parameters names to their values.
    exact_params
        If True, only known parameters are accepted. Initially those defined in the
        class attribute :attr:`PARAMS_NAMES`, but others can be added dynamically in
        :attr:`allowed_parameters`. Other parameters will raise exceptions. Default is
        False.
    kwargs
        Other parameters values in the form ``name=value``.
        Parameters will be taken in order of first available in:
        ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
    """

    SHORTNAME: str | None = None
    """Short name to refer to this dataset class."""
    ID: str | None = None
    """Long name to identify uniquely this dataset class."""

    PARAMS_NAMES: Sequence[Hashable] = []
    """List of known parameters names."""
    PARAMS_DEFAULTS: dict = {}
    """Default values of parameters.

    Optional. Can be used to define default values for parameters local to a
    dataset, (*ie* that are not defined in project-wide
    :class:`ParametersManager`).
    """

    FILE_MANAGER_CLASS = FileManagerAbstract
    LOADER_CLASS = LoaderAbstract
    WRITER_CLASS = WriterAbstract

    def __init__(
        self,
        params: Mapping[str, Any] | Scheme | None = None,
        exact_params: bool = False,
        **kwargs,
    ):
        self.exact_params: bool = exact_params
        """Only known parameters are accepted if true."""
        self.params: dict[str, Any] = {}
        """Mapping of current parameters values.

        They should be changed by using :meth:`set_params` to void the cached values
        appropriately.
        """
        self.allowed_params = set(self.PARAMS_NAMES)
        """Mutable set of allowed parameters.

        We may add to it from parameters found in the filename structure for instance.
        """

        # Set parameters
        # No reset cache (nothing cached yet)
        # No check (validity might be affected by modules)
        self.set_params(params, **kwargs, _reset=False, _check=False)

        # initialize modules
        self.file_manager = self.FILE_MANAGER_CLASS(self)
        self.loader = self.LOADER_CLASS(self)
        self.writer = self.WRITER_CLASS(self)

        # Now that everything is in place, we check our parameters
        self.check_known_param(self.params)

    def __str__(self) -> str:
        """Return a string representation."""
        name = []
        if self.SHORTNAME is not None:
            name.append(self.SHORTNAME)
        if self.ID is not None:
            name.append(self.ID)

        clsname = self.__class__.__name__
        if name:
            clsname = f" ({clsname})"

        return ":".join(name) + clsname

    def __repr__(self) -> str:
        """Return a human readable representation."""
        s = []
        s.append(self.__str__())
        s.append("Parameters:")
        s.append(f"\tdefined: {self.PARAMS_NAMES}")
        if self.PARAMS_DEFAULTS:
            s.append(f"\tdefaults: {self.PARAMS_DEFAULTS}")
        s.append(f"\tallowed: {self.allowed_params}")
        s.append(f"\tset: {self.params}")

        if self.file_manager is not None:
            s += str(self.file_manager).splitlines()

        return "\n".join(s)

    def set_params(
        self,
        params: Mapping[str, Any] | Scheme | None = None,
        _reset: bool = True,
        _check: bool = True,
        **kwargs,
    ):
        """Set parameters values.

        Parameters
        ----------
        params:
            Mapping of the parameters names to their values.
        _reset
            Desactivate cleaning the cache if False.
        _check
            Desactivate checking parameters if False.
        kwargs:
            Other parameters values in the form ``name=value``.
            Parameters will be taken in order of first available in:
            ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        if params is None:
            params = {}
        elif isinstance(params, Scheme):
            params = dict(params.values_recursive())
        else:
            params = dict(params)  # shallow copy
        params = params | self.PARAMS_DEFAULTS
        params.update(kwargs)

        self.params.update(params)
        if _reset:
            self.clean_cache()
        if _check:
            self.check_known_param(params)

    def check_known_param(self, params: Iterable[str]):
        """Check if the parameters are known to this dataset class.

        A 'known parameter' is one present in :attr:`PARAMS_NAMES` or defined
        in the filename pattern (as a varying group).

        Only run the check if :attr:`exact_params` is True.
        """
        if not self.exact_params:
            return
        for p in params:
            if p not in self.allowed_params:
                raise KeyError(f"Parameter '{p}' was not expected for dataset {self}")

    def clean_cache(self) -> None:
        """Clean the cache of all modules."""
        for mod in [self.file_manager, self.loader, self.writer]:
            mod.clean_cache()

    @property
    def datafiles(self) -> list[str]:
        """Get available datafiles."""
        return self.file_manager.datafiles

    def get_filename(self, **fixes) -> str:
        """Create a filename corresponding to a set of parameters values.

        All parameters must be defined, either with the instance :attr:`params`,
        or with the ``fixes`` arguments.

        Parameters
        ----------
        fixes:
            Parameters to fix to specific values. Override :attr:`params` values.
        """
        return self.file_manager.get_filename(**fixes)

    def get_data(self, ignore_postprocess: bool = False, **kwargs: Any) -> Any:
        """Return data.

        Gather all files corresponding to set parameters and load that data through
        :meth:`load_data`.

        If the :meth:`Dataset.postprocess_dataset` is defined and
        ``ignore_postprocess`` is not True, the method is applied to data.

        Parameters
        ----------
        ignore_postprocess
            If True, do not apply postprocess function. Default is False.
        kwargs:
            Arguments passed to function loading data.
        """
        return self.loader.get_data(
            self.datafiles, ignore_postprocess=ignore_postprocess, **kwargs
        )

    def get_data_sets(
        self,
        params_maps: Sequence[Mapping[str, Any]] | None = None,
        params_sets: Sequence[Sequence] | None = None,
        ignore_postprocess: bool = False,
        **kwargs,
    ) -> Any:
        """Return data for specific sets of parameters.

        Each set of parameter will specify one filename. Parameters that do not change
        from one set to the next do not need to be specified if they are fixed (by
        setting them in the Dataset). The sets can be specified with either one of
        `params_maps` or `params_sets`.

        Parameters
        ----------
        params_maps
            Each set is specified by a mapping of parameters names to a value::

                [{'Y': 2020, 'm': 1, 'd': 15},
                 {'Y': 2021, 'm': 2, 'd': 24},
                 {'Y': 2022, 'm', 6, 'd': 2}]

            This will give 3 filenames for 3 different dates. Note that here, the
            parameters do not need to be the same for all sets, for example in a fourth
            set we could have ``{'Y': 2023, 'm': 1, 'd': 10, 'depth': 50}`` to override
            the value of 'depth' set in the Dataset parameters.
        params_sets
            Here each set is specified by sequence of parameters values. This first row
            gives the order of parameters. The same input as before can be written as::

                [['Y', 'm', 'd'],
                 [2020, 1, 15],
                 [2021, 2, 24],
                 [2022, 6, 2]]

            Here the changing parameters must remain the same for the whole sequence.
        ignore_postprocess
            If True, do not apply postprocess function. Defaults to False.
        kwargs
            Arguments passed to function loading data.
        """
        if params_sets is not None and params_maps is not None:
            raise KeyError("Cannot specify both params_sets and params_maps")
        if params_sets is None and params_maps is None:
            raise KeyError("Must at least specify one of params_sets or params_maps")

        if params_sets is not None:
            dims = params_sets[0]
            if not all(isinstance(x, str) for x in dims):
                raise TypeError(f"Dimensions names must be strings, got: {dims}")

            params_maps = []
            for p_set in params_sets[1:]:
                params_maps.append(dict(zip(dims, p_set, strict=True)))

        assert params_maps is not None
        datafiles = [self.get_filename(**p_map) for p_map in params_maps]

        return self.loader.get_data(
            datafiles, ignore_postprocess=ignore_postprocess, **kwargs
        )

    def postprocess_data(self, data: Any) -> Any:
        """Apply any action on the data after opening it.

        By default, raises NotImplementedError and thus the postprocess will be ignored.
        """
        raise NotImplementedError()


class DatasetDefault(DatasetAbstract):
    """Multi-file dataset to open/write with Xarray."""

    OPEN_MFDATASET_KWARGS: dict[str, Any] = {}
    """Arguments passed to :func:`xarray.open_mfdataset`."""

    FILE_MANAGER_CLASS = FileFinderManager
    LOADER_CLASS = XarrayLoader
    WRITER_CLASS = XarrayWriter
    # vv this is for typechecking vv
    file_manager: FileFinderManager
    loader: XarrayLoader
    writer: XarrayWriter

    def get_root_directory(self) -> str | PathLike | Iterable[str]:
        """Return the directory containing all datafiles.

        Can return a path, or an iterable of directories that will automatically be
        joined.
        """
        raise NotImplementedError()

    def get_filename_pattern(self) -> str:
        """Return the filename pattern.

        See the Filefinder documentation on the syntax:
        `https://filefinder.readthedocs.io/en/latest/find_files.html`.
        """
        raise NotImplementedError()


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

    def __call__(self, cls: type[DatasetAbstract]):
        """Apply decorator."""
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
