"""Loader module."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .module import Module

if TYPE_CHECKING:
    import xarray as xr


class LoaderAbstract(Module):
    """Abstract class of Loader module.

    Defines the minimal API to communicate with the parent :class:`DatasetAbstract` and
    other modules.

    The Loader is tasked with opening the data into Python.
    It may run post-processing if defined by the user.
    """

    def get_data(self, source: Any, ignore_postprocess: bool = False, **kwargs) -> Any:
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
        data = self.load_data(source, **kwargs)

        if ignore_postprocess:
            return data

        try:
            data = self.run_on_dataset("postprocess_data", data)
        except NotImplementedError:
            pass
        return data

    def load_data(self, source: Any, **kwargs) -> Any:
        """Load the data from datafiles."""
        return NotImplementedError("Subclasses must override this method.")


class XarrayLoader(LoaderAbstract):
    """Loader for Multifile Xarray.

    Uses :func:`xarray.open_mfdataset` to open data.
    """

    TO_DEFINE_ON_DATASET = ["OPEN_MFDATASET_KWARGS", "preprocess_data"]

    def load_data(self, source: Sequence[str], **kwargs) -> xr.Dataset:
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

        kwargs = self.get_attr_dataset("OPEN_MFDATASET_KWARGS") | kwargs
        ds = xr.open_mfdataset(source, **kwargs)
        return ds
