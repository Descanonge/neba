from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import xarray as xr

from data_assistant.util import check_output_path

from .file_manager import FileFinderManager
from .module import Module

if TYPE_CHECKING:
    import xarray as xr


class WriterAbstract(Module):
    pass


class XarrayWriter(WriterAbstract):
    time_fixable = set('YBmdjHMSFxX')
    """Parameters names we consider as time related."""

    def write(
        self, ds: xr.Dataset, /, *, by_variables: Mapping, encoding: dict, **kwargs
    ):
        """Write data to disk.

        Manage 'time' coordinate appropriately. Maybe. Hopefully.
        """
        pass

    def write_by_fixable(
        self,
        ds,
        squeeze=False,
        **kwargs,
    ):
        """Use fixable parameters to guess how to group.

        Anything fixable is 'outer', the rest of coordinates are inner.

        Squeeze could be choice in {'drop', True, False}
        (remove completely, squeeze, leave coord of dim 1)
        """
        if not isinstance(self.dataset.file_manager, FileFinderManager):
            raise TypeError('File manager must be of type FileFinderManager')
        fixable = set(self.dataset.file_manager.fixable_params)

        # If we have a time dimension, we must check related group names
        if 'time' in ds.dims and fixable & self.time_fixable:
            fixable.add('time')
            fixable -= self.time_fixable

        # Check that fixable parameters have an associated dimension
        for p in fixable:
            if p not in ds.dims:
                raise KeyError(f"Parameter '{p}' has no associated dimension.")

        # Generate list of filenames
        stack_vars = list(fixable)
        stacked = ds.stack(__filename_vars__=stack_vars)

        for ds_unit in stacked.groupby('__filename_vars__'):
            ds_unit = ds_unit.unstack()

            # Find fixable parameters values. They should all be of dimension 1.
            # Note .values.item() to retrieve a scalar
            fixable_values = {dim: ds_unit.coords[dim].values.item() for dim in fixable}
            outfile = self.dataset.get_filename(**fixable_values)

            # Check existence of containing directory (and create it if necessary)
            check_output_path(outfile)

            # Apply squeeze argument
            if squeeze:
                ds_unit = ds_unit.squeeze(stack_vars, drop=(squeeze == 'drop'))

            # To file
            # TODO Out to deal with different files, we need different methods call :(
            # That could be a dataset attribute, like OUTPUT_FORMAT
            # TODO Same thing for delayed computation or not ? But this might
            # better be something more dynamic, like an argument to the write calls.
            # But this could get hairy if we have many write methods.
            ds.to_netcdf(outfile, **kwargs)
