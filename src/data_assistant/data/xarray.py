"""Plugin definitions for XArray."""

from __future__ import annotations

import itertools
import logging
import os
import typing as t
from collections import abc

import xarray as xr

from .loader import LoaderPluginAbstract
from .writer import WriterPluginAbstract

if t.TYPE_CHECKING:
    try:
        from dask.delayed import Delayed
        from distributed import Client
    except ImportError:
        Delayed = None  # type: ignore
        Client = None  # type: ignore
    try:
        from zarr.storage import BaseStore
    except ImportError:
        BaseStore = None  # type: ignore

    CallXr = tuple[str, xr.Dataset]


log = logging.getLogger(__name__)

## Loading


class XarrayFileLoaderPlugin(LoaderPluginAbstract[str, xr.Dataset]):
    """Loader for a single file to Xarray.

    Uses :func:`xarray.open_dataset` to open data.
    """

    OPEN_DATASET_KWARGS: dict[str, t.Any] = {}

    def load_data_concrete(self, source: str, **kwargs) -> xr.Dataset:
        """Return a dataset object.

        The dataset is obtained from :func:`xarray.open_mfdataset`.

        Parameters
        ----------
        source:
            Sequence of files containing data.
        kwargs:
            Arguments passed to :func:`xarray.open_dataset`. They will take precedence
            over the default values of the class attribute :attr:`OPEN_DATASET_KWARGS`.
        """
        import xarray as xr

        kwargs = self.OPEN_DATASET_KWARGS | kwargs
        ds = xr.open_dataset(source, **kwargs)
        return ds


class XarrayMultiFileLoaderPlugin(LoaderPluginAbstract[abc.Sequence[str], xr.Dataset]):
    """Loader for multiple files to Xarray.

    Uses :func:`xarray.open_mfdataset` to open data.
    """

    OPEN_MFDATASET_KWARGS: dict[str, t.Any] = {}

    def load_data_concrete(self, source: abc.Sequence[str], **kwargs) -> xr.Dataset:
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


## Writing


class XarrayWriterPlugin(WriterPluginAbstract[str, xr.Dataset]):
    """Write Xarray dataset to single target.

    Implement the single call method, and common features for other
    """

    TO_NETCDF_KWARGS: dict[str, t.Any] = {}
    """Arguments passed to the function writing files."""

    TO_ZARR_KWARGS: dict[str, t.Any] = {}
    """Arguments passed to the writing function for zarr stores."""

    def _guess_format(self, filename: str) -> t.Literal["nc", "zarr"]:
        _, ext = os.path.splitext(filename)
        if ext:
            format = ext.removeprefix(".")
            if format not in ["nc", "zarr"]:
                raise ValueError(f"Unsupported format extension '{ext}'")
            return t.cast(t.Literal["nc", "zarr"], format)
        raise ValueError(f"Could not find file extension for '{filename}'")

    @t.overload
    def send_single_call(
        self,
        call: CallXr,
        format: t.Literal[None] = ...,
        compute: t.Literal[True] = ...,
        **kwargs,
    ) -> None | BaseStore: ...

    @t.overload
    def send_single_call(
        self,
        call: CallXr,
        format: t.Literal["nc"],
        compute: t.Literal[True],
        **kwargs,
    ) -> None: ...

    @t.overload
    def send_single_call(
        self,
        call: CallXr,
        format: t.Literal["zarr"],
        compute: t.Literal[True],
        **kwargs,
    ) -> BaseStore: ...

    @t.overload
    def send_single_call(
        self,
        call: CallXr,
        *,
        compute: t.Literal[False],
        **kwargs,
    ) -> Delayed: ...

    def send_single_call(
        self,
        call: CallXr,
        format: t.Literal["nc", "zarr", None] = None,
        compute: bool = True,
        **kwargs,
    ) -> Delayed | None | BaseStore:
        """Execute a single call.

        Parameters
        ----------
        kwargs
            Passed to the writing function.
        """
        outfile, ds = call
        if format is None:
            format = self._guess_format(outfile)

        kwargs["compute"] = compute

        log.debug("Sending single call to %s", outfile)
        if format == "nc":
            kwargs = self.TO_NETCDF_KWARGS | kwargs
            return ds.to_netcdf(outfile, **kwargs)

        if format == "zarr":
            kwargs = self.TO_ZARR_KWARGS | kwargs
            return ds.to_zarr(outfile, **kwargs)

        t.assert_never(format)

    def set_metadata(
        self,
        ds: xr.Dataset,
        params: dict | str | None = None,
        add_dataset_parameters: bool = True,
        add_commit: bool = True,
    ) -> xr.Dataset:
        """Set some dataset attributes with information on how it was created.

        Wrapper around :meth:`get_metadata`.
        Attributes already present will not be overwritten.

        Parameters
        ----------
        ds
            Dataset to add global attributes to. This is **not** done in-place.
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
            add_dataset_params=add_dataset_parameters,
            add_commit=add_commit,
        )
        # Do not overwrite attributes.
        for k in set(ds.attrs.keys()) & set(meta.keys()):
            meta.pop(k)
        return ds.assign_attrs(**meta)

    def write(  # type: ignore[override]
        self,
        data: xr.Dataset,
        target: str | None = None,
        **kwargs,
    ) -> t.Any:
        """Write data to target.

        Currently, target can be a netcdf file, or zarr store.
        Directories are created as needed. Metadata is added to the dataset.

        Parameters
        ----------
        data
            Dataset to write.
        target
            If None (default), target location is automatically obtained via
            :meth:`.DataManagerBase.get_source`.
        kwargs
            Passed to the function that writes to disk
            (:meth:`xarray.Dataset.to_netcdf` or :meth:`xarray.Dataset.to_zarr`).
        """
        if target is None:
            target = self.get_source()

        data = self.set_metadata(data)
        call = target, data
        self.check_directory(call)
        return self.send_single_call(call, **kwargs)


class XarrayMultiFileWriterPlugin(XarrayWriterPlugin):
    """Write from an xarray dataset to multiple files using Dask."""

    def send_calls_together(
        self,
        calls: abc.Sequence[tuple[str, xr.Dataset]],
        client: Client,
        chop: int | None = None,
        format: t.Literal["nc", "zarr", None] = None,
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
            Passed to writing function. Overwrites the defaults from
            :attr:`TO_NETCDF_KWARGS`, whatever the value of `function` is.
        """
        import distributed

        self.check_overwriting_calls(calls)
        self.check_directories(calls)

        ncalls = len(calls)
        if chop is None:
            chop = ncalls

        slices = cut_slices(ncalls, chop)
        log.info("%d total calls in %d groups.", ncalls, len(slices))

        kwargs = self.TO_NETCDF_KWARGS | kwargs
        kwargs["compute"] = False

        for slc in slices:
            log.info("\tslice %s", slc)

            grouped_calls = calls[slc]
            delayed = [self.send_single_call(c, **kwargs) for c in grouped_calls]

            # Compute them all at once
            # This loop is super important, this create all the futures for computation
            # and remove them as soon as they are completed (and the variable `future`
            # goes out of scope). That way the data does not pile up, it is freed.
            # We only care about the side effect of writing to disk, not the result data.
            for future in distributed.as_completed(client.compute(delayed)):
                log.debug("\t\tfuture completed: %s", future)

    def write(  # type: ignore[override]
        self,
        data: abc.Sequence[xr.Dataset],
        target: list[str] | None = None,
        client: Client | None = None,
        **kwargs,
    ) -> t.Any:
        """Write datasets to multiple targets.

        Each dataset is written to its corresponding target (filename or store
        location). Directories will automatically be created if necessary. Metadata is
        added to the dataset.

        Parameters
        ----------
        data
            Sequence of datasets to write.
        target
            If None (default), target locations are automatically obtained via
            :meth:`.DataManagerBase.get_source`.
        client:
            Dask :class:`distributed.Client` instance. If present multiple write calls
            will be send in parallel. See :meth:`send_calls_together` for details.
            If left to None, the write calls will be sent serially.
        kwargs
            Passed to the function that writes to disk
            (:meth:`xarray.Dataset.to_netcdf` or :meth:`xarray.Dataset.to_zarr`).
        """
        if target is None:
            target = self.get_source()

        data = [self.set_metadata(d) for d in data]

        if len(target) != len(data):
            raise IndexError(
                f"Number of writing targets ({len(target)}) differing from "
                f"number of datasets ({len(data)})"
            )
        calls = list(zip(target, data))

        self.check_directories(calls)
        self.check_overwriting_calls(calls)
        if client is None:
            # TODO no return value
            return self.send_calls(calls, **kwargs)
        return self.send_calls_together(calls, client, **kwargs)


T = t.TypeVar("T", covariant=True)


class Splitable(t.Protocol[T]):
    """Protocol for a source plugin that can split data into multiple sources.

    The plugin manages input/output sources. Initially made for multifile datasets.
    A number of parameters can be left :meth:`unfixed` which allows to have many files
    (for instance, if we do not "fix" the parameter *year*, we can have files for any
    year we want).

    It must also implement a :meth:`get_filename` method that returns a filename when
    given a specific set of values (those that were left unfixed).

    The idea is that a plugin can split data according to the parameters that are left
    unfixed (example by year), once the data is split we find the associated filename
    for each year and we then write to files.

    The protocol is generic and allows for any type of source.
    """

    @property
    def unfixed(self) -> abc.Iterable[T]:
        """Iterable of parameters that are not fixed.

        This must take into account the values that are specified (or not) in the
        data-manager parameters.
        """
        ...

    def get_filename(self, **fixes: t.Any) -> T:
        """Return a filename corresponding to this set of values.

        This must also take into account values that are already specified in the
        data-manager parameters (that are not present in the *fixes* argument).
        """


class XarraySplitWriterPlugin(XarrayMultiFileWriterPlugin, Splitable[str]):
    """Writer for Xarray datasets in multifiles.

    Can automatically split a dataset to the corresponding files by communicating
    with a source plugin that implement the :class:`HasUnfixed` protocol.
    This is meant to work for :class:`.FileFinderManager`.

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
    """List of correspondance between pattern names and pandas frequencies.

    The pattern names are arranged in increasing order.
    """

    def write(  # type: ignore[override]
        self,
        data: xr.Dataset,
        target: None = None,
        time_freq: str | bool = True,
        squeeze: bool | str | abc.Mapping[abc.Hashable, bool | str] = False,
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
        data
            Data to write.
        target:
            Cannot be used here. Use :class:`.XarrayMultiFileWriterPlugin` instead.
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
        if target is not None:
            raise ValueError("Target files cannot be specified using the SplitWriter.")

        datasets_by_fix = self.split_by_unfixed(data)

        datasets_by_all = []
        for dataset in datasets_by_fix:
            datasets_by_all += self.split_by_time(dataset, time_freq=time_freq)

        calls = self.to_calls(datasets_by_all, squeeze=squeeze)

        if client is None:
            self.send_calls(calls, **kwargs)
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
        params:
            Parameters to replace for writing data.

        Returns
        -------
        List of datasets

        """
        unfixed = set(self.unfixed)
        # Only keep time related unfixed
        unfixed &= set(self.time_intervals_groups)

        # not time dimension or no unfixed params in filename pattern
        if "time" not in ds.dims or not unfixed:
            log.debug("Not splitting by time.")
            return [ds]

        # user asked to not resample
        if not time_freq:
            return [ds_unit for _, ds_unit in ds.groupby("time", squeeze=False)]

        if isinstance(time_freq, str):
            # User defined
            freq = time_freq
        else:
            # we guess from pattern
            # time_intervals_groups is sorted by period, first hit is smallest period
            for grp in self.time_intervals_groups:
                if grp in unfixed:
                    freq = self.time_intervals_groups[grp]
                    break

        log.debug("Split with frequency %s", freq)

        infreq = xr.infer_freq(ds.time)
        if infreq is not None and infreq == freq:
            log.debug(
                "Resampling frequency is equal to that of dataset. "
                "Will not resample."
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
        unfixed -= set(self.time_intervals_groups)

        # Remove unfixed not associated to a coordinate
        unfixed -= set(f for f in unfixed if f not in ds.coords)

        # We could check here if there are associated dimensions or parameters to
        # each unfixed

        # No parameter to split
        if not unfixed:
            return [ds]

        log.debug("Split by parameters %s", unfixed)

        stack_vars = list(unfixed)
        stacked = ds.stack(__filename_vars__=stack_vars)

        out = [ds_unit.unstack() for _, ds_unit in stacked.groupby("__filename_vars__")]

        return out

    def to_calls(
        self,
        datasets: abc.Sequence[xr.Dataset],
        squeeze: bool | str | abc.Mapping[abc.Hashable, bool | str] = False,
    ) -> list[CallXr]:
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
        present_time_fix = unfixed & set(self.time_intervals_groups)
        unfixed -= set(self.time_intervals_groups)

        calls: list[CallXr] = []
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
            if isinstance(squeeze, abc.Mapping):
                for d, sq in squeeze.items():
                    if sq:
                        ds = ds.squeeze(d, drop=(sq == "drop"))
            else:
                if squeeze:
                    ds = ds.squeeze(None, drop=(squeeze == "drop"))

            calls.append((outfile, ds))

        return calls


def cut_slices(total_size: int, slice_size: int) -> list[slice]:
    """Return list of slices of size at most ``slice_size``."""
    slices = itertools.starmap(
        slice,
        itertools.pairwise(itertools.chain(range(0, total_size, slice_size), [None])),
    )
    return list(slices)
