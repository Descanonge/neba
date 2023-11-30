from __future__ import annotations

import itertools
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from data_assistant.util import check_output_path

from .file_manager import FileFinderManager
from .module import Module

if TYPE_CHECKING:
    import xarray as xr
    from distributed import Client

    Call = tuple[xr.Dataset, str]

log = logging.getLogger(__name__)


class WriterAbstract(Module):
    pass


class XarrayWriter(WriterAbstract):
    time_fixable = 'YBmdjHMSFxX'
    """Parameters names we consider as time related."""

    def write(
        self, ds: xr.Dataset, /, *, by_variables: Mapping, encoding: dict, **kwargs
    ):
        """Write data to disk.

        Manage 'time' coordinate appropriately. Maybe. Hopefully.
        """
        pass

    def cut_by_fixable(
        self,
        ds: xr.Dataset,
        squeeze=False,
    ) -> list[Call]:
        """Use parameters in the filename pattern to guess how to group.

        Any fixable parameter is 'outer' (different values will be in different
        files), the rest of coordinates are inner.

        Squeeze could be choice in {'drop', True, False}
        (remove completely, squeeze, leave coord of dim 1)
        """
        if not isinstance(self.dataset.file_manager, FileFinderManager):
            raise TypeError('File manager must be of type FileFinderManager')
        fixable = set(self.dataset.file_manager.fixable_params)

        # If we have time-related fixable, we must do some work
        if 'time' in ds.dims and (present_time_fix := fixable & set(self.time_fixable)):
            # find values for those parameters
            for param in present_time_fix:
                values = ds.time.dt.strftime(param)
                ds = ds.assign_coords({param: ('time', values)})

            # We mark time as fixable
            fixable.add('time')
            fixable -= present_time_fix

        # Check that fixable parameters have an associated dimension
        for p in fixable:
            if p not in ds.dims:
                raise KeyError(f"Parameter '{p}' has no associated dimension.")

        # Generate list of filenames
        stack_vars = list(fixable)
        stacked = ds.stack(__filename_vars__=stack_vars)

        calls: list[tuple[xr.Dataset, str]] = []
        for _, ds_unit in stacked.groupby('__filename_vars__'):
            ds_unit = ds_unit.unstack()

            # Find fixable parameters values. They should all be of dimension 1.
            # Note .values.item() to retrieve a scalar
            fixable_values = {dim: ds_unit.coords[dim].values.item() for dim in fixable}
            outfile = self.dataset.get_filename(**fixable_values)

            # Check existence of containing directory (and create it if necessary)
            check_output_path(outfile)

            # Remove time fixable dimensions we added
            ds = ds.drop_dims(present_time_fix)

            # Apply squeeze argument
            if squeeze:
                ds_unit = ds_unit.squeeze(stack_vars, drop=(squeeze == 'drop'))

            calls.append((ds_unit, outfile))

        return calls

    def check_overwriting_calls(self, calls: Sequence[Call]):
        """Check if some calls have the same filename."""
        outfiles = [f for _, f in calls]
        duplicates = []
        for f in set(outfiles):
            if outfiles.count(f) > 1:
                duplicates.append(f)

        if duplicates:
            raise ValueError(
                f'Multiple writing calls to the same filename·s: {duplicates}'
            )

    def send_calls(self, calls: Sequence[Call], **kwargs):
        self.check_overwriting_calls(calls)

        for call in calls:
            self.send_single_call(call, **kwargs)

    def send_delayed_calls(
        self,
        calls: Sequence[Call],
        client: Client,
        chop: int | None = None,
        **kwargs,
    ):
        import distributed

        self.check_overwriting_calls(calls)
        ncalls = len(calls)
        if chop is None:
            chop = ncalls

        slices = cut_slices(ncalls, chop)
        log.info('%d total calls in %d groups.', ncalls, len(slices))

        # This create delayed objects when calling function
        kwargs['compute'] = False

        for slc in slices:
            log.debug('\tslice %s', slc)

            # Select calls and turn it into a list of delayed objects for Dask
            grouped_calls = calls[slc]
            delayed = [self.send_single_call(c, **kwargs) for c in grouped_calls]

            # Compute them all at once
            # This loop is super important, this create all the futures for computation
            # and remove them as soon as they are completed (and the variable `future`
            # goes out of scope). That way the data does not pile up, it is freed.
            # We only care about the side effect of writing to disk, not the result data.
            for future in distributed.as_completed(client.compute(delayed)):
                log.debug('\t\tfuture completed: %s', future)

    def send_single_call(self, call: Call, **kwargs):
        # To file
        # TODO Out to deal with different files, we need different methods call :(
        # That could be a dataset attribute, like OUTPUT_FORMAT
        ds, outfile = call
        return ds.to_netcdf(outfile, **kwargs)


def cut_slices(total_size: int, slice_size: int) -> list[slice]:
    slices = itertools.starmap(
        slice,
        itertools.pairwise(itertools.chain(range(0, total_size, slice_size), [None])),
    )
    return list(slices)
