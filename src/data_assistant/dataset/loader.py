from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .module import Module

if TYPE_CHECKING:
    import xarray as xr


class LoaderAbstract(Module):
    def get_data(self, **kwargs: Any) -> Any:
        """Return data.

        The function :func:`postprocess_dataset` is then applied to the dataset.
        (By default, this function does nothing).

        Parameters
        ----------
        kwargs:
            Arguments passed to function loading data.
        """
        raise NotImplementedError("Subclass must implement this method.")


class XarrayLoader(LoaderAbstract):
    TO_DEFINE_ON_DATASET = ["OPEN_MFDATASET_KWARGS"]

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
        import xarray as xr

        kwargs = self.get_attr_dataset("OPEN_MFDATASET_KWARGS") | kwargs
        datafiles = self.dataset.datafiles
        ds = xr.open_mfdataset(datafiles, **kwargs)
        ds = self.run_on_dataset("postprocess_data", ds)
        return ds
