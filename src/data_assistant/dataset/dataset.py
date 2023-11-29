"""Dataset objects.

The Dataset object is the main entry point for the user. By subclassing it,
they can adapt it to their data quickly.

If we want to retain the ability to define a new dataset just by subclassing
the main class, this makes splitting features into different classes challenging.
I still tried to use composition and delegate some work by modules: FileManager,
Loader, and Writer. These retain a reference to the Dataset and can invoke
attributes and methods from it, which can be user-defined in a subclass.

I tried to stay agnostic to how a module may work to possibility accomodate for
different data formats, sources, etc. A minimal API is written in each abstract
class.
It may still be quite geared towards multifiles-netcdf, since this is what I use.
But hopefully it should be easy to swap modules without breaking everything.

The parameters management is kept in the Dataset object for simplicity, maybe it
could be done by a module of its own, if this is necessary.

Modules all inherit from .util.Module, which features a caching system, with
even some attribute that can generate a new value on the fly in case of a cache
miss (see AutoCachedProperty). This was done to avoid numerous repetitions when
dealing with multi-files scanners.
The Dataset can trigger a flush of all caches.
"""

from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Any

from .file_manager import FileFinderManager, FileManagerAbstract
from .loader import LoaderAbstract, XarrayLoader
from .writer import WriterAbstract, XarrayWriter


class DatasetAbstract:
    SHORTNAME: str | None = None
    """Short name to refer to this dataset class."""
    ID: str | None = None
    """Long name to identify uniquely this dataset class."""

    PARAMS_NAMES: Sequence[Hashable] = []
    """List of parameters names."""
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
        params: Mapping[str, Any] | None = None,
        exact_params: bool = False,
        **kwargs,
    ):
        self.exact_params: bool = exact_params
        self.params: dict[str, Any] = {}
        """Mapping of parameters values."""
        self.allowed_params = set(self.PARAMS_NAMES)
        """Mutable copy of the list of allowed parameters.

        We may add to it from parameters found in the filename structure.
        """

        # Set parameters
        # this is initialization: we do not reset cache
        # also no check, validity may be changed by the file_manager
        self.set_params(params, **kwargs, _reset=False, _check=False)

        # initialize modules
        self.file_manager = self.FILE_MANAGER_CLASS(self)
        self.loader = self.LOADER_CLASS(self)
        self.writer = self.WRITER_CLASS(self)

        # Now that everything is in place, we check our parameters
        self._check_param_known(self.params)


    def __str__(self) -> str:
        name = []
        if self.SHORTNAME is not None:
            name.append(self.SHORTNAME)
        if self.ID is not None:
            name.append(self.ID)

        clsname = self.__class__.__name__
        if name:
            clsname = f' ({clsname})'

        return ':'.join(name) + clsname

    def __repr__(self) -> str:
        s = []
        s.append(self.__str__())
        s.append('Parameters:')
        s.append(f'\tdefined: {self.PARAMS_NAMES}')
        if self.PARAMS_DEFAULTS:
            s.append(f'\tdefaults: {self.PARAMS_DEFAULTS}')
        s.append(f'\tallowed: {self.allowed_params}')
        s.append(f'\tset: {self.params}')

        if self.file_manager is not None:
            s += str(self.file_manager).splitlines()

        return '\n'.join(s)

    def set_params(self, params: Mapping[str, Any] | None = None,
                   _reset: bool = True, _check: bool = True,
                   **kwargs):
        """Set parameters values.

        Parameters
        ----------
        params:
            Mapping of parameters values.
        kwargs:
            Parameters values. Will take precedence over ``params``.
            Parameters will be taken in order of first available in:
            ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        if params is None:
            params = {}
        params = dict(params)  # shallow copy
        params = params | self.PARAMS_DEFAULTS
        params.update(kwargs)

        self.params = params
        if _reset:
            self._reset_cached_properties()
        if _check:
            self._check_param_known(params)

    def _check_param_known(self, params: Iterable[str]):
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

    def _reset_cached_properties(self) -> None:
        if self.file_manager is not None:
            self.file_manager._reset_cached_properties()
        # do this for others

    def get_datafiles(self) -> list[str]:
        """Get available datafiles."""
        return self.file_manager.get_datafiles()

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


class DatasetBase(DatasetAbstract):
    OPEN_MFDATASET_KWARGS: dict[str, Any] = {}
    """Arguments passed to :func:`xarray.open_mfdataset`."""

    FILE_MANAGER_CLASS = FileFinderManager
    LOADER_CLASS = XarrayLoader
    WRITER_CLASS = XarrayWriter
