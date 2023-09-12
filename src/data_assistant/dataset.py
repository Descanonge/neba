"""Dataloader object."""

import os
from collections.abc import Hashable, Sequence
from os import path

import xarray as xr
from filefinder import Finder

PathLike = str | os.PathLike


class DataLoaderAbstract:
    """DataLoader abstract base.

    Subclass to specify a new dataset.
    Each subclass stores information about a dataset: the parameters it
    varies with, the root directory containing the datafiles, the filename
    pattern of those files,...

    Each instance allow to get those informations for a specific set of
    parameters, specified at instanciation, or with :func:`set_params`.

    .. note::

        Some properties are cached to avoid overhead. Changing parameters
        voids the cache.

    Methods to override when subclassing (in simple, basic cases) include:
    :func:`_get_root_directory`, :func:`get_filename_pattern`,
    :func:`_get_data`, :func:`postprocess_dataset`.
    """

    SHORTNAME: str
    ID: str | None

    PARAMS_NAMES: Sequence[Hashable]
    """List of parameters names."""
    PARAMS_DEFAULTS: dict = {}
    """Default values of parameters.

    Optional. Can be used to define parameters local to a dataset, that are not
    defined in project-wide :class:`ParametersManager`.

    Parameters
    ----------
    params:
        Mapping of parameters values.
    kwargs:
        Parameters values. Will take precedence over ``params``.
        Parameters will be taken in order of first available in:
        ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
    """
    OPEN_MFDATASET_KWARGS: dict = {}
    """Arguments passed to :func:`xarray.open_mfdataset`."""

    _CACHED_PROPERTIES = ['filefinder', 'fixable_params', 'datafiles']

    def __init__(self,
                 params: Mapping | None = None,
                 exact_params: bool = False,
                 **kwargs):
        # Definitions for type checking and documentation
        self.params: dict
        """Mapping of parameters values."""
        self.root_directory: str
        """Root directory containing data."""
        self.filename_pattern: str
        """Filename pattern used to find files using :mod:`filefinder`."""

        # Cached properties
        self._filefinder: Finder | None
        self._fixable_params: list[str] | None
        self._datafiles: list[str] | None

        self.exact_params: bool = exact_params

        self.set_params(params, **kwargs)

    def set_params(self, params: Mapping[str, Any] | None = None, **kwargs):
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

        self._check_param_known(params)

        self.params = params
        self._reset_cached_properties()

    def _reset_cached_properties(self) -> None:
        for prop in self._CACHED_PROPERTIES:
            setattr(self, '_'+prop, None)

    def _check_param_known(self, params: Iterable[str]):
        if not self.exact_params:
            return
        for p in params:
            if p not in self.PARAMS_NAMES:
                raise KeyError(f'Parameter {p} was not expected for dataset'
                                f' {self.SHORTNAME} {self.PARAMS_NAMES}.')

    @property
    def filefinder(self) -> Finder:
        if self._filefinder is None:
            self._filefinder = self.get_filefinder()
        return self._filefinder

    @property
    def fixable_params(self) -> list[str]:
        if self._fixable_params is None:
            self._fixable_params = self._find_fixable_params(self.filefinder)
        return self._fixable_params

    @property
    def datafiles(self) -> list[str]:
        if self._datafiles is None:
            self._datafiles = self.get_datafiles()
        return self._datafiles

    @staticmethod
    def _find_fixable_params(finder) -> list[str]:
        groups_names = [g.name for g in finder.groups]
        # remove doublons
        return list(set(groups_names))

    def _get_root_directory(self) -> str | list[str]:
        """Redefine me!"""
        raise NotImplementedError()

    def get_root_directory(self) -> str:
        root_dir = self._get_root_directory()
        if not isinstance(root_dir, str):
            root_dir = path.join(*root_dir)
        return root_dir

    def get_filename_pattern(self) -> str:
        """Redefine me!"""
        raise NotImplementedError()

    def get_filename(self, **fixes) -> PathLike:
        self._check_param_known(fixes)
        fixes_params = {p: self.params[p] for p in self.fixable_params}
        fixes.update(fixes_params)
        filename = self.filefinder.make_filename(fixes)
        return filename

    def get_filefinder(self) -> Finder:
        root_dir = self.get_root_directory()
        pattern = self.get_filename_pattern()
        finder = Finder(root_dir, pattern)

        # we do not use self.fixable_params directly because it needs
        # self.get_filefinder to be defined
        fixable_params = self._find_fixable_params(finder)
        for p, value in self.params.items():
            if p in fixable_params:
                finder.fix_group(p, value)

        return finder

    def get_datafiles(self) -> list[str]:
        return self.filefinder.get_files()

    def get_data(self, **kwargs) -> xr.Dataset:


        kwargs = self.OPEN_MFDATASET_KWARGS | kwargs
        ds = xr.open_mfdataset(self.datafiles, **kwargs)
        ds = self.postprocess_dataset(ds)
        return ds

    def postprocess_dataset(self, ds: xr.Dataset) -> xr.Dataset:
        """Redefine me!"""
        return ds


class DataLoaderSST(DataLoaderAbstract):
    SHORTNAME = 'CCI-C3S SST'
    PARAMS_NAMES = ['region', 'days', 'Y', 'm', 'd']
    OPEN_MFDATASET_KWARGS = dict(parallel=True)

    DATA_ROOTDIR = '/data/chaeck/'

    def _get_root_directory(self):
        rootdir = [
            self.DATA_ROOTDIR,
            self.params['region'],
            '{}days'.format(self.params['days'])
        ]
        return rootdir

    def get_filename_pattern(self):
        return '%(Y)/SST_%(Y)%(m)%(d).nc'

    def postprocess_dataset(self, ds):
        ds['analysed_sst'] = ds.analysed_sst + 273.15
        return ds
