"""Writer module: write data to disk."""

from __future__ import annotations

import inspect
import itertools
import json
import logging
import os
import socket
import subprocess
from collections.abc import Hashable, Mapping, Sequence
from datetime import datetime
from os import path
from typing import TYPE_CHECKING, Any

from filefinder.group import TIME_GROUPS

from .dataset import Module
from .file_manager import FileFinderModule

if TYPE_CHECKING:
    import xarray as xr
    from distributed import Client

    # TODO make a generic ? to have different dataset types
    Call = tuple[xr.Dataset, str]

log = logging.getLogger(__name__)


class WriterModuleAbstract(Module):
    """Abstract class of Writer module.

    Manages metadata to (eventually) add to data before writing.
    """

    def get_metadata(
        self,
        params: dict | str | None = None,
        add_dataset_params: bool = True,
        add_commit: bool = True,
    ) -> dict[str, Any]:
        """Set some dataset attributes with information on how it was created.

        Attributes are:

        * ``written_as_dataset:`` name of dataset class.
        * ``created_by``: hostname and filename of the python script used
        * ``created_with_params``: a string representing the parameters,
        * ``created_on``: date of creation
        * ``created_at_commit``: if found, the current/HEAD commit hash.

        Parameters
        ----------
        params
            A dictionnary of the parameters used, that will automatically be serialized
            as a string. Can also be a custom string.
            Presentely we first try a serialization using json, if that fails, `str()`.
        add_dataset_params
            Add the parent dataset parameters values to serialization if True (default)
            and if ``parameters`` is not a string. The parent parameters won't overwrite
            the values of ``parameters``.
        add_commit
            If True (default), try to find the current commit hash of the directory
            containing the script called.
        """
        meta = {}

        # Name of class
        cls_name = self.__class__.__name__
        if self.ID:
            cls_name += f":{self.ID}"
        meta["written_as_dataset"] = cls_name

        # Get hostname and script name
        hostname = socket.gethostname()
        script = inspect.stack()[1].filename
        meta["created_by"] = f"{hostname}:{script}"

        # Get parameters as string
        if params is not None:
            if isinstance(params, str):
                params_str = params
            else:
                if add_dataset_params:
                    params = self.params | params
                try:
                    params_str = json.dumps(params)
                except TypeError:
                    params_str = str(params)

            meta["created_with_params"] = params_str

        # Get date
        meta["created_on"] = datetime.today().strftime("%x %X")

        # Get commit hash
        if add_commit:
            # Use the directory of the calling script
            gitdir = path.dirname(script)
            cmd = ["git", "-C", gitdir, "rev-parse", "HEAD"]
            ret = subprocess.run(cmd, capture_output=True, text=True)
            if ret.returncode == 0:
                commit = ret.stdout.strip()
                meta["created_at_commit"] = commit
            else:
                log.debug("'%s' not a valid git directory", gitdir)

        return meta


class XarrayWriterModule(WriterModuleAbstract):
    """Writer for Xarray datasets.

    For simple unique calls.
    The source should be compatible with a unique :meth:`xr.Dataset.to_netcdf` call.
    """

    TO_NETCDF_KWARGS: dict[str, Any] = {}

    def set_metadata(
        self,
        ds: xr.Dataset,
        /,
        params: dict | str | None = None,
        add_dataset_parameters: bool = True,
        add_commit: bool = True,
    ) -> xr.Dataset:
        """Set some dataset attributes with information on how it was created.

        Wrapper around :meth:`get_metadata`.

        Parameters
        ----------
        ds
            Dataset to add global attributes to. This is done in-place.
        params
            A dictionnary of the parameters used, that will automatically be serialized
            as a string. Can also be a custom string.
            Presentely we first try a serialization using json, if that fails, `str()`.
        add_dataset_params
            Add the parent dataset parameters values to serialization if True (default)
            and if ``parameters`` is not a string. The parent parameters won't overwrite
            the values of ``parameters``.
        add_commit
            If True (default), try to find the current commit hash of the directory
            containing the script called.
        """
        meta = self.get_metadata(
            params=params,
            add_dataset_params=add_dataset_parameters,
            add_commit=add_commit,
        )
        ds.attrs.update(meta)
        return ds

    def write(
        self,
        ds: xr.Dataset,
        /,
        *,
        params: dict,
        **kwargs,
    ):
        """Write to netcdf file.

        File is obtained from parent dataset. Directories are created as needed.
        Metadata is added to the dataset.

        Parameters
        ----------
        params:
            Mapping of parameters to obtain filename.
        kwargs:
            Passed to the function that writes to disk
            (:meth:`xarray.Dataset.to_netcdf`).
        """
        outfile = self.get_source(**params)
        ds = self.set_metadata(ds, params=params)
        call = ds, outfile
        self.check_directories([call])
        return self.send_single_call(call, **kwargs)

    def send_single_call(self, call: Call, **kwargs):
        """Execute a single call.

        Parameters
        ----------
        kwargs
            Passed to the writing function.
        """
        # To file
        # TODO Out to deal with different files, we need different methods call :(
        # That could be a dataset attribute, like OUTPUT_FORMAT
        ds, outfile = call
        kwargs = kwargs | self.TO_NETCDF_KWARGS
        return ds.to_netcdf(outfile, **kwargs)

    def check_directories(self, calls: Sequence[Call]):
        """Check if directories are missing, and create them if necessary."""
        files = [f for _, f in calls]

        # Keep only the containing directories, with no duplicate
        directories = set()
        for f in files:
            directories.add(path.dirname(f))

        for d in directories:
            if not path.isdir(d):
                log.debug("Creating output directory %s", d)
                os.makedirs(d)


class XarrayMultifileWriterModule(XarrayWriterModule):
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
        """Send multiple calls serially.

        Parameters
        ----------
        kwargs
            Passed to writing function.
        """
        self.check_overwriting_calls(calls)
        self.check_directories(calls)

        for call in calls:
            self.send_single_call(call, **kwargs)

    def send_calls_together(
        self,
        calls: Sequence[Call],
        client: Client,
        chop: int | None = None,
        **kwargs,
    ):
        """Send multiple calls together.

        If Dask is correctly configured, the writing calls will be executed in parallel.

        For all calls within a group, a list of delayed writing calls is constructed.
        It is then computed all at once using ``client.compute(delayed)``, however to
        avoid lingering results (because we only care about the side-effect of writing
        to file, not the computed result), we get rid of 'futures' as soon as completed.
        This avoid a blow up in memory::

            for future in distributed.as_completed(client.compute(delayed)):
                log.debug("future completed: %s", future)

        Parameters
        ----------
        client
            Dask :class:`Client` instance.
        chop
            If None (default), all calls are sent together. If chop is an integer,
            groups of calls of size ``chop`` (at most) will be sent one after the other,
            calls within each group being run in parallel.
        kwargs
            Passed to writing function.

        """
        import distributed

        self.check_overwriting_calls(calls)
        self.check_directories(calls)
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


# Note that we inherit from FileFinderMixin, but it could be changed to any
# MultiFileMixin that has an attribute `unfixed: list[str]`.
# Can't be bothered to deal with mypy antics now though.


class XarraySplitWriterModule(XarrayMultifileWriterModule, FileFinderModule):
    """Writer for Xarray datasets in multifiles.

    Can automatically split a dataset to the corresponding files by communicating
    directory with a :class:`FileFinderManager`.

    The time dimension is treated on its own because of its complexity and because
    the user can manually specify the desired time resolution of the files (otherwise
    we will try to guess using the filename pattern). Resampling will be avoided if we
    can simply loop over the time dimension (desired frequency equals data frequency).

    The dimensions names must correspond to pattern parameters.

    All the resulting writing operations, the 'calls', can be executed serially
    (default behavior) or be submitted in parallel using Dask. They can all be sent
    all at once (``chop=None``, default) or limited to parallels groups of smaller
    size that will run serially.

    Both parts (of splitting the xarray dataset and sending calls) can be used
    separately, if there is a need for more flexibility or missing features.
    """

    time_intervals_groups = dict(
        S="S",
        X="S",
        M="min",
        H="H",
        j="D",
        d="D",
        x="D",
        F="D",
        m="MS",
        B="MS",
        Y="YS",
    )
    """List of correspondance between pattern names and pandas frequencies."""

    def write(
        self,
        ds: xr.Dataset,
        /,
        *,
        time_freq: str | bool = True,
        squeeze: bool | str | Mapping[Hashable, bool | str] = False,
        client: Client | None = None,
        chop: int | None = None,
        **kwargs,
    ):
        """Write data to disk.

        First split datasets following the parameters that vary in the filename pattern.
        Then split all datasets obtained along the time dimension (if present), and
        according to the ``time_freq`` argument.
        The dimensions left of size one are squeezed according to the argument value.

        Each cut dataset is written to its corresponding filename. Directories will
        automatically be created if necessary.

        Parameters
        ----------
        time_freq:
            If it is a string, use it as a frequency/period for
            :meth:`xarray.Dataset.resample`. For example ``M`` will return datasets
            grouped by month. See this page
            `https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#period-aliases`
            for details on period strings. If the frequency of the dataset is the same
            as the target one, it will not be resampled to avoid unecessary work.
            There might be false positives (offsets maybe ?). In which case you should
            resample before manually, and set `time_freq` to false.

            If False: do not resample, just return a list with one dataset for each time
            index.

            If True the frequency will be guessed from the filename pattern. The
            smallest period present will be used.
        squeeze:
            How to squeeze dimensions of size one. If False, dimensions are left as is.
            If True, squeeze. If equal to "drop", the squeezed coordinate is dropped
            instead of being kept as a scalar.

            This can be configured by dimension with a mapping of each dimension to a
            squeeze argument.
        client:
            Dask :class:`distributed.Client` instance. If present multiple write calls
            will be send in parallel. See :meth:`send_calls_together` for details.
            If left to None, the write calls will be sent serially.
        chop
            If None (default), all calls are sent together. If chop is an integer,
            groups of calls of size ``chop`` (at most) will be sent one after the other,
            calls within each group being run in parallel.
        kwargs:
            Passed to the function that writes to disk
            (:meth:`xarray.Dataset.to_netcdf`).
        """
        datasets_by_fix = self.split_by_unfixed(ds)

        datasets_by_all = []
        for dataset in datasets_by_fix:
            datasets_by_all += self.split_by_time(dataset, time_freq=time_freq)

        calls = self.to_calls(datasets_by_all, squeeze=squeeze)

        if client is None:
            self.send_calls(calls)
        else:
            self.send_calls_together(calls, client, chop=chop, **kwargs)

    def split_by_time(
        self,
        ds: xr.Dataset,
        time_freq: str | bool = True,
    ) -> list[xr.Dataset]:
        """Split dataset in time groups.

        If the frequency of the dataset is the same as the target one, it will not be
        resampled to avoid unecessary work. There might be false positives (offsets
        maybe ?). In which case you should resample before manually, and set `time_freq`
        to false.

        Parameters
        ----------
        time_freq:
            If it is a string, use it as a frequency/period for
            :meth:`xarray.Dataset.resample`. For example ``M`` will return datasets
            grouped by month. See `this page
            <https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#period-aliases>`_
            for details on period strings.

            If False: do not resample, just return a list with one dataset for each time
            index.

            If True the frequency will be guessed from the filename pattern. The
            smallest period present will be used.

        Returns
        -------
        List of datasets

        """
        import xarray as xr

        unfixed = set(self.unfixed)
        # Only keep time related unfixed
        unfixed &= set(TIME_GROUPS)

        # not time dimension or no unfixed params in filename pattern
        if "time" not in ds.dims or not unfixed:
            return [ds]

        # user asked to not resample
        if not time_freq:
            return [ds_unit for _, ds_unit in ds.groupby("time", squeeze=False)]

        if isinstance(time_freq, str):
            # User defined
            freq = time_freq
        else:
            # we guess from pattern
            # TIME_GROUPS is sorted by period, first hit is smallest period
            for t in TIME_GROUPS:
                if t in unfixed:
                    freq = self.time_intervals_groups[t]
                    break

        infreq = xr.infer_freq(ds.time)
        if infreq is not None and infreq == freq:
            log.debug(
                "Resampling frequency is equal to that of dataset (%s). "
                "Will not resample.",
                freq,
            )
            return [ds_unit for _, ds_unit in ds.groupby("time", squeeze=False)]

        resample = ds.resample(time=freq)
        return [ds_unit for _, ds_unit in resample]

    def split_by_unfixed(self, ds: xr.Dataset) -> list[xr.Dataset]:
        """Use parameters in the filename pattern to guess how to group.

        The dataset is split in sub-datasets such that each sub-dataset correspond
        to a unique combinaison of unfixed parameter values which will give a
        unique filename.

        Coordinates whose name does not correspond to an unfixed group in the filename
        pattern will be written entirely in each file.
        """
        unfixed = set(self.unfixed)
        # Remove time related unfixeds
        unfixed -= set(TIME_GROUPS)

        # Remove unfixed not associated to a coordinate
        unfixed -= set(f for f in unfixed if f not in ds.coords)

        # We could check here if there are associated dimensions or parameters to
        # each unfixed

        # No parameter to split
        if not unfixed:
            return [ds]

        stack_vars = list(unfixed)
        stacked = ds.stack(__filename_vars__=stack_vars)

        out = [ds_unit.unstack() for _, ds_unit in stacked.groupby("__filename_vars__")]

        return out

    def to_calls(
        self,
        datasets: Sequence[xr.Dataset],
        squeeze: bool | str | Mapping[Hashable, bool | str] = False,
    ) -> list[Call]:
        """Transform sequence of datasets into writing calls.

        A writing call being a tuple of a dataset and the filename to write it to.

        Parameters
        ----------
        squeeze:
            How to squeeze dimensions of size one. If False, dimensions are left as is.
            If True, squeeze. If equal to "drop", the squeezed coordinate is dropped
            instead of being kept as a scalar.

            This can be configured by dimensions with a mapping of dimensions to
            a squeeze argument.
        """
        unfixed = set(self.unfixed)
        # Set time fixes apart
        present_time_fix = unfixed & set(TIME_GROUPS)
        unfixed -= set(TIME_GROUPS)

        calls: list[Call] = []
        for ds in datasets:
            # Find unfixed parameters values. They should all be of dimension 1.
            # Note .values.item() to retrieve a scalar
            # We need some trickery for time related parameters
            unfixed_values = {}
            for dim in unfixed:
                if dim in ds.coords:
                    val = ds.coords[dim].values.item()
                else:
                    val = self.params[dim]
                unfixed_values[dim] = val

            # If there are time values, we simply get the first one
            if present_time_fix and "time" in ds.dims:
                for p in present_time_fix:
                    value = ds.time[0].dt.strftime(f"%{p}").values.item()
                    unfixed_values[p] = value

            outfile = self.get_filename(**unfixed_values)

            # Apply squeeze argument
            if isinstance(squeeze, Mapping):
                for d, sq in squeeze.items():
                    if sq:
                        ds = ds.squeeze(d, drop=(sq == "drop"))
            else:
                if squeeze:
                    ds = ds.squeeze(None, drop=(squeeze == "drop"))

            calls.append((ds, outfile))

        return calls


def cut_slices(total_size: int, slice_size: int) -> list[slice]:
    """Return list of slices of size at most ``slice_size``."""
    slices = itertools.starmap(
        slice,
        itertools.pairwise(itertools.chain(range(0, total_size, slice_size), [None])),
    )
    return list(slices)
