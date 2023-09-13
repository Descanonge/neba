"""Dataloader object."""

import functools
import os
from collections.abc import Hashable, Iterable, Mapping, Sequence
from os import path
from typing import Any

import xarray as xr
from filefinder import Finder


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

    Parameters
    ----------
    params:
        Mapping of parameters values.
    kwargs:
        Parameters values. Will take precedence over ``params``.
        Parameters will be taken in order of first available in:
        ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
    exact_params:
        If True, only parameters explicitly defined in ``PARAMS_NAMES`` are
        allowed. Default is False: unknown parameters are kept. They will not be
        passed to the filefinder object.
    """

    SHORTNAME: str | None = None
    ID: str | None = None

    PARAMS_NAMES: Sequence[Hashable] = []
    """List of parameters names."""
    PARAMS_DEFAULTS: dict = {}
    """Default values of parameters.

    Optional. Can be used to define default values for parameters local to a
    dataset, (*ie* that are not defined in project-wide
    :class:`ParametersManager`).
    """
    OPEN_MFDATASET_KWARGS: dict = {}
    """Arguments passed to :func:`xarray.open_mfdataset`."""

    _CACHED_PROPERTIES = ['filefinder', 'fixable_params', 'datafiles']

    def __init__(self,
                 params: Mapping | None = None,
                 exact_params: bool = False,
                 **kwargs):
        self.params: dict = dict()
        """Mapping of parameters values."""

        # Cached properties
        self._filefinder: Finder | None = None
        self._fixable_params: list[str] | None = None
        self._datafiles: list[str] | None = None

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
    def root_directory(self) -> str:
        """Root directory containing data."""
        rootdir = self.get_root_directory()
        if not isinstance(rootdir, (str, os.PathLike)):
            rootdir = path.join(*rootdir)
        return rootdir

    @property
    def filename_pattern(self) -> str:
        """Filename pattern used to find files using :mod:`filefinder`."""
        return self.get_filename_pattern()

    @property
    def filefinder(self) -> Finder:
        """Filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.
        """
        if self._filefinder is None:
            self._filefinder = self.get_filefinder()
        return self._filefinder

    @property
    def fixable_params(self) -> list[str]:
        """List of parameters that vary in the filefinder object.

        Found automatically from a :attr:`filefinder` instance.
        """
        if self._fixable_params is None:
            self._fixable_params = self._find_fixable_params(self.filefinder)
        return self._fixable_params

    @property
    def datafiles(self) -> list[str]:
        """List of datafiles to open.

        This property is the cached result of :func:`get_datafiles`.
        """
        if self._datafiles is None:
            self._datafiles = self.get_datafiles()
        return self._datafiles

    @staticmethod
    def _find_fixable_params(finder) -> list[str]:
        groups_names = [g.name for g in finder.groups]
        # remove doublons
        return list(set(groups_names))

    def get_root_directory(self) -> str | list[str]:
        """Return directory containing datafiles.

        Returns either the directory path, or a list of directories that will be
        joined together using :func:`os.path.join`.
        """
        raise NotImplementedError()

    def get_filename_pattern(self) -> str:
        """Return the datafiles filenames pattern.

        The pattern specifies how the filenames are structured: which parts
        vary and how.
        For details on the syntax, see :external+filefinder:doc:`find_files`.
        """
        raise NotImplementedError()

    def get_filename(self, **fixes) -> str:
        """Create a filename corresponding to a set of parameters values.

        All parameters must be defined, with this instance :attr:`params`,
        or with the ``fixes`` arguments.

        Parameters
        ----------
        fixes:
            Parameters to fix to specific values. Will take precedence
            over the instance :attr:`params` attribute.
        """
        self._check_param_known(fixes)
        fixes_params = {p: self.params[p] for p in self.fixable_params}
        fixes.update(fixes_params)
        filename = self.filefinder.make_filename(fixes)
        return filename

    def get_filefinder(self) -> Finder:
        """Return a filefinder instance to scan for datafiles.

        Any parameter corresponding to a group in the pattern is fixed to
        that parameter's value.

        Is also used to create filenames for a specific set of parameters.
        """

        # we do not use self.fixable_params directly because it needs
        # self.get_filefinder to be defined
        fixable_params = self._find_fixable_params(finder)
        for p, value in self.params.items():
            if p in fixable_params:
                finder.fix_group(p, value)

        finder = Finder(self.root_directory, self.filename_pattern)
        return finder

    def get_datafiles(self) -> list[str]:
        """Scan and return files corresponding to pattern.

        Use the :attr:`filefinder` object to scan for files corresponding to
        the filename pattern.
        """
        return self.filefinder.get_files()

    def get_data(self, **kwargs) -> xr.Dataset:
        """Return a dataset object.

        The dataset is obtained from :func:`xarray.open_mfdataset` applied to
        the files found using :func:`get_datafiles`.

        The function :func:`postprocess_dataset` is then applied to the dataset.
        (By default, this function does nothing).

        Parameters
        ----------
        kwargs:
            Arguments passed to :func:`xarray.open_mfdataset`. They will
            take precedence over the class default values in
            :attr:`OPEN_MFDATASET_KWARGS`.
        """
        kwargs = self.OPEN_MFDATASET_KWARGS | kwargs
        ds = xr.open_mfdataset(self.datafiles, **kwargs)
        ds = self.postprocess_dataset(ds)
        return ds

    def postprocess_dataset(self, ds: xr.Dataset) -> xr.Dataset:
        """Apply any action on the dataset after opening it.

        By default, just return the dataset without doing anything (*ie* the
        identity function).
        """
        return ds


class DataLoadersMap(dict):
    """Mapping of registered DataLoaders.

    Maps ID and/or SHORTNAME to a DataLoaderAbstract subclass.

    DataLoaders classes are stored using their unique ID, or SHORTNAME if not
    defined. They can be retrieved using ID or SHORTNAME, as preferred.
    """

    def __init__(self, *args: type[DataLoaderAbstract]):
        # create empty dict
        super().__init__()

        self.shortnames: list[str] = []
        self.ids_for_shortnames: list[str] = []

        for dl in args:
            self.add_dataloader(dl)

    def add_dataloader(self, dl: type[DataLoaderAbstract]):
        """Register a DataLoaderAbstract subclass."""
        if dl.ID is not None:
            key = dl.ID
            key_type = 'ID'
        elif dl.SHORTNAME is not None:
            key = dl.SHORTNAME
            key_type = 'SHORTNAME'
        else:
            raise TypeError(f'No ID or SHORTNAME defined in class {dl}')

        if key in self:
            raise KeyError(f'DataLoader key {key_type}:{key} already exists.')

        if dl.SHORTNAME is not None:
            self.shortnames.append(dl.SHORTNAME)
            self.ids_for_shortnames.append(key)

        super().__setitem__(key, dl)

    def __getitem__(self, key: str) -> type[DataLoaderAbstract]:
        """Return DataLoaderAbstract subclass with this ID or SHORTNAME."""
        if key in self.shortnames:
            if self.shortnames.count(key) > 1:
                raise KeyError(f'More than one DataLoader with SHORTNAME: {key}')
            idx = self.shortnames.index(key)
            key = self.ids_for_shortnames[idx]
        return super().__getitem__(key)


class register:
    def __init__(self, mapping: DataLoadersMap):
        self.mapping = mapping

    def __call__(self,
                 subclass: type[DataLoaderAbstract]
                 ) -> type[DataLoaderAbstract]:
        self.mapping.add_dataloader(subclass)
        return subclass


mapping = DataLoadersMap()


@register(mapping)
class DataLoaderSST(DataLoaderAbstract):
    ID = 'CCI-C3S SST'
    SHORTNAME = 'SST'
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
