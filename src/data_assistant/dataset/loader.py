from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .module import Module

if TYPE_CHECKING:
    import xarray as xr


class LoaderAbstract(Module):
    def _get_data(
        self, datafiles: Sequence[str], ignore_postprocess: bool = False, **kwargs
    ) -> Any:
        data = self.load_data(datafiles, **kwargs)

        if ignore_postprocess:
            return data

        try:
            data = self.run_on_dataset("postprocess_data", data)
        except NotImplementedError:
            pass
        return data

    def load_data(self, datafiles: Sequence[str], **kwargs) -> Any:
        """Load the data from datafiles."""
        return NotImplementedError("Subclasses must override this method.")


class XarrayLoader(LoaderAbstract):
    TO_DEFINE_ON_DATASET = ["OPEN_MFDATASET_KWARGS", "preprocess_data"]

    def load_data(self, datafiles: Sequence[str], **kwargs) -> xr.Dataset:
        """Return a dataset object.

        The dataset is obtained from :func:`xarray.open_mfdataset`.

        Parameters
        ----------
        kwargs:
            Arguments passed to :func:`xarray.open_mfdataset`. They will
            take precedence over the class default values in
            :attr:`OPEN_MFDATASET_KWARGS`.
        """
        import xarray as xr

        kwargs = self.get_attr_dataset("OPEN_MFDATASET_KWARGS") | kwargs
        ds = xr.open_mfdataset(datafiles, **kwargs)
        return ds
