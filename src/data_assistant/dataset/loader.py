"""Loader module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic
from .dataset import Module, _DataT, _SourceT

if TYPE_CHECKING:
    import xarray as xr


class LoaderModuleAbstract(Generic[_DataT, _SourceT], Module):
    """Abstract class of Loader module.

    Defines the minimal API to communicate with the parent :class:`DatasetAbstract` and
    other modules.

    The Loader is tasked with opening the data into Python.
    It may run post-processing if defined by the user.
    """

    def load_data(
        self, source: _SourceT, ignore_postprocess: bool = False, **kwargs
    ) -> _DataT:
        """Load data and run post-processing.

        Uses :meth:`load_data` that can be overwritten by subclasses.

        Tries to run the method ``postprocess_data`` of the parent dataset. If it raises
        NotImplementedError, postprocess will be ignored.

        Parameters
        ----------
        source
            Source location of the data to load.
        ignore_postprocess
            If True, do not apply postprocessing. Default is False.
        kwargs:
            Arguments passed to function loading data.

        """
        data = self.load_data_concrete(source, **kwargs)

        if ignore_postprocess:
            return data

        try:
            data = self.postprocess_data(data)
        except NotImplementedError:
            pass
        return data

    def postprocess_data(self, data: _DataT) -> _DataT:
        raise NotImplementedError("Implement on your DatasetBase subclass.")

    def load_data_concrete(self, source: _SourceT, **kwargs) -> Any:
        """Load the data from datafiles."""
        return NotImplementedError("Implement in Mixin subclass.")


class XarrayMultiFileLoaderModule(LoaderModuleAbstract):
    """Loader for Multifile Xarray.

    Uses :func:`xarray.open_mfdataset` to open data.
    """

    OPEN_MFDATASET_KWARGS: dict[str, Any] = {}

    def load_data_concrete(self, source: Any, **kwargs) -> xr.Dataset:
        """Return a dataset object.

        The dataset is obtained from :func:`xarray.open_mfdataset`.

        Parameters
        ----------
        source:
            Sequence of files containing data.
        kwargs:
            Arguments passed to :func:`xarray.open_mfdataset`. They will
            take precedence over the default values of the class attribute
            :attr:`OPEN_MFDATASET_KWARGS`.
        """
        import xarray as xr

        kwargs = self.OPEN_MFDATASET_KWARGS | kwargs
        ds = xr.open_mfdataset(source, **kwargs)
        return ds
