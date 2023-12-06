from __future__ import annotations

import inspect
import itertools
import json
import logging
import socket
import subprocess
from collections.abc import Iterable, Sequence
from datetime import datetime
from os import path
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

    time_fixable = 'SXMHjdxFmBY'
    time_intervals_groups = dict(
        S='S',
        X='S',
        M='min',
        H='H',
        j='D',
        d='D',
        x='D',
        F='D',
        m='MS',
        B='MS',
        Y='YS',
    )

    TO_DEFINE_ON_DATASET = ["TO_NETCDF_KWARGS"]

    def write(
        self,
        ds: xr.Dataset,
        /,
        *,
        encoding: dict,
        time_freq: str | None = None,
        squeeze: str = 'squeeze',  # allow config by dimensions
        client: Client | None = None,
        **kwargs,
    ):
        """Write data to disk.

        Manage 'time' coordinate appropriately. Maybe. Hopefully.
        """
        datasets_by_fix = self.cut_by_fixable(ds)

        datasets_by_all = []
        for dataset in datasets_by_fix:
            datasets_by_all += self.cut_by_time(dataset, time_freq=time_freq)

        calls = self.to_calls(datasets_by_all, squeeze=squeeze)

        if client is None:
            self.send_calls(calls)
        else:
            self.send_delayed_calls(calls, client, **kwargs)

    def set_metadata(
        self,
        ds: xr.Dataset,
        /,
        parameters: dict | str | None = None,
        add_commit: bool = True,
    ) -> xr.Dataset:
        """Set some dataset attributes with information on how it was created.

        Attributes are:
        - "created_by": hostname and filename of the python script used
        - "created_with_params": a string representing the parameters,
        - "created_on": date of creation
        - "created_at_commit": if found, the current/HEAD commit hash.

        Parameters
        ----------
        ds:
            Dataset to add global attributes to. This is done in-place.

        Parameters
        ----------
            A dictionnary of the parameters used, that will automatically be serialized
            as a string. Can also be a custom string.
            Presentely we first try a serialization using json, if that fails, `str()`.
        add_commit:
            If True (default), try to find the current commit hash of the directory
            containing the script called.
        """
        # Get hostname and script name
        hostname = socket.gethostname()
        script = inspect.stack()[1].filename
        ds.attrs["created_by"] = f"{hostname}:{script}"

        # Get parameters as string
        if parameters is not None:
            if isinstance(parameters, str):
                params_str = parameters
            else:
                try:
                    params_str = json.dumps(parameters)
                except TypeError:
                    params_str = str(parameters)

            ds.attrs["created_with_params"] = params_str

        # Get date
        ds.attrs["created_on"] = datetime.today().strftime("%x %X")

        # Get commit hash
        if add_commit:
            # Use the directory of the calling script
            gitdir = path.dirname(script)
            cmd = ["git", "-C", gitdir, "rev-parse", "HEAD"]
            ret = subprocess.run(cmd, capture_output=True, text=True)
            if ret.returncode == 0:
                commit = ret.stdout.strip()
                ds.attrs["created_at_commit"] = commit
            else:
                log.debug("'%s' not a valid git directory", gitdir)

        return ds

    def cut_by_time(
        self,
        ds: xr.Dataset,
        time_freq: str | None,
    ) -> list[xr.Dataset]:
        fixable = self.get_fixable()
        # Only keep time related fixable
        fixable &= set(self.time_fixable)

        if "time" not in ds.dims or not fixable:
            return [ds]

        if time_freq is None:
            return [ds_unit for _, ds_unit in ds.groupby("time")]

        # Guess frequency from fixables
        # User could specify frequency also
        resample = ds.resample(time="MS")

        out = [ds_unit for _, ds_unit in resample]
        return out


    def cut_by_fixable(self, ds: xr.Dataset) -> list[xr.Dataset]:
        """Use parameters in the filename pattern to guess how to group.

        Any fixable parameter is 'outer' (different values will be in different
        files), the rest of coordinates are inner.

        Squeeze could be choice in {'drop', True, False}
        (remove completely, squeeze, leave coord of dim 1)
        """
        fixable = self.get_fixable()
        # Remove time related fixables
        fixable -= set(self.time_fixable)

        # Check that fixable parameters have an associated dimension
        for p in fixable:
            if p not in ds.coords:
                raise KeyError(f"Parameter '{p}' has no associated dimension.")

        # Generate list of filenames
        stack_vars = list(fixable)
        stacked = ds.stack(__filename_vars__=stack_vars)

        out = [ds_unit.unstack() for _, ds_unit in stacked.groupby('__filename_vars__')]

        return out


    def get_fixable(self):
        if not isinstance(self.dataset.file_manager, FileFinderManager):
            raise TypeError("File manager must be of type FileFinderManager")
        fixable = set(self.dataset.file_manager.fixable_params)
        return fixable


    def to_calls(
        self,
        datasets: Sequence[xr.Dataset],
        squeeze: str = 'ye'
    ):
        fixable = self.get_fixable()
        present_time_fix = fixable & set(self.time_fixable)
        # Remove time related fixables
        fixable -= set(self.time_fixable)

        calls: list[Call] = []
        for ds in datasets:
            # Find fixable parameters values. They should all be of dimension 1.
            # Note .values.item() to retrieve a scalar
            # We need some trickery for time related parameters
            fixable_values = {}
            for dim in fixable:
                fixable_values[dim] = ds.coords[dim].values.item()

            # If there are time values, we simply get the first one
            if present_time_fix and "time" in ds.dims:
                for p in present_time_fix:
                    value = ds.time[0].dt.strftime(f"%{p}").values.item()
                    fixable_values[p] = value

            outfile = self.dataset.get_filename(**fixable_values)

            # Apply squeeze argument
            if squeeze:
                ds = ds.squeeze(None, drop=(squeeze == "drop"))

            calls.append((ds, outfile))

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
                f"Multiple writing calls to the same filename·s: {duplicates}"
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
        log.info("%d total calls in %d groups.", ncalls, len(slices))

        # This create delayed objects when calling function
        kwargs["compute"] = False

        for slc in slices:
            log.debug("\tslice %s", slc)

            # Select calls and turn it into a list of delayed objects for Dask
            grouped_calls = calls[slc]
            delayed = [self.send_single_call(c, **kwargs) for c in grouped_calls]

            # Compute them all at once
            # This loop is super important, this create all the futures for computation
            # and remove them as soon as they are completed (and the variable `future`
            # goes out of scope). That way the data does not pile up, it is freed.
            # We only care about the side effect of writing to disk, not the result data.
            for future in distributed.as_completed(client.compute(delayed)):
                log.debug("\t\tfuture completed: %s", future)

    def send_single_call(self, call: Call, **kwargs):
        # To file
        # TODO Out to deal with different files, we need different methods call :(
        # That could be a dataset attribute, like OUTPUT_FORMAT
        ds, outfile = call
        kwargs = kwargs | self.get_attr_dataset('TO_NETCDF_KWARGS')
        return ds.to_netcdf(outfile, **kwargs)


def cut_slices(total_size: int, slice_size: int) -> list[slice]:
    slices = itertools.starmap(
        slice,
        itertools.pairwise(itertools.chain(range(0, total_size, slice_size), [None])),
    )
    return list(slices)
