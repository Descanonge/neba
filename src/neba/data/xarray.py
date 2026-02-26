"""Modules for XArray."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, cast, overload

import xarray as xr

from neba.utils import cut_in_slices

from .loader import LoaderAbstract
from .writer import SplitWriterMixin, WriterAbstract

if TYPE_CHECKING:
    try:
        from dask.delayed import Delayed
        from distributed import Client
    except ImportError:
        Delayed = None  # type: ignore
        Client = None  # type: ignore

    CallXr = tuple[str, xr.Dataset]


log = logging.getLogger(__name__)


class XarrayLoader(LoaderAbstract[str | os.PathLike, xr.Dataset]):
    """Load from single source with Xarray.

    Uses :func:`xarray.open_dataset` or :func:`xarray.open_mfdataset` to open data.
    """

    open_dataset_kwargs: dict[str, Any] = {}
    """Options passed to :func:`xarray.open_dataset`. :meth:`.DataInterface.get_data`
    kwargs take precedence."""

    open_mfdataset_kwargs: dict[str, Any] = {}
    """Options passed to :func:`xarray.open_mfdataset`. :meth:`.DataInterface.get_data`
    kwargs take precedence."""

    def preprocess(self) -> Callable[[xr.Dataset], xr.Dataset]:
        """Return a function to preprocess data.

        If ``preprocess`` in :attr:`open_mfdataset_kwargs` is True, the function will be
        used for the corresponding `open_mfdataset` argument. The function should take
        in and return a dataset.
        """
        raise NotImplementedError

    def load_data_concrete(
        self,
        source: str | os.PathLike | Sequence[str | os.PathLike],
        **kwargs: Any,
    ) -> xr.Dataset:
        """Load data.

        Parameters
        ----------
        source:
            Sequence of files containing data.
        kwargs:
            Arguments passed to :func:`xarray.open_dataset`. They will take precedence
            over the default values of the class attribute :attr:`open_dataset_kwargs`
            and :attr:`open_mfdataset_kwargs`.
        """
        if isinstance(source, str | os.PathLike):
            kwargs = self.open_dataset_kwargs | kwargs
            ds = xr.open_dataset(source, **kwargs)
        else:
            kwargs = self.open_mfdataset_kwargs | kwargs
            if kwargs.get("preprocess", False) is True:
                kwargs["preprocess"] = self.preprocess()
            ds = xr.open_mfdataset(source, **kwargs)

        return ds


class XarrayWriter(WriterAbstract[str, xr.Dataset]):
    """Write Xarray dataset."""

    to_netcdf_kwargs: dict[str, Any] = {}
    """Arguments passed to the function writing files."""

    to_zarr_kwargs: dict[str, Any] = {}
    """Arguments passed to the writing function for zarr stores."""

    def _guess_format(self, filename: str) -> Literal["nc", "zarr"]:
        _, ext = os.path.splitext(filename)
        if ext:
            format = ext.removeprefix(".")
            if format not in ["nc", "zarr"]:
                raise ValueError(f"Unsupported format extension '{ext}'")
            return cast(Literal["nc", "zarr"], format)
        raise ValueError(f"Could not find file extension for '{filename}'")

    @overload
    def send_single_call(
        self,
        call: CallXr,
        format: Literal[None] = ...,
        compute: Literal[True] = ...,
        **kwargs: Any,
    ) -> None | xr.backends.ZarrStore: ...

    @overload
    def send_single_call(
        self,
        call: CallXr,
        format: Literal["nc"],
        compute: Literal[True],
        **kwargs: Any,
    ) -> None: ...

    @overload
    def send_single_call(
        self,
        call: CallXr,
        format: Literal["zarr"],
        compute: Literal[True],
        **kwargs: Any,
    ) -> xr.backends.ZarrStore: ...

    @overload
    def send_single_call(
        self,
        call: CallXr,
        *,
        compute: Literal[False],
        **kwargs: Any,
    ) -> Delayed: ...

    def send_single_call(
        self,
        call: CallXr,
        format: Literal["nc", "zarr", None] = None,
        compute: bool = True,
        **kwargs: Any,
    ) -> Delayed | None | xr.backends.ZarrStore:
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
            kwargs = self.to_netcdf_kwargs | kwargs
            return ds.to_netcdf(outfile, **kwargs)

        if format == "zarr":
            kwargs = self.to_zarr_kwargs | kwargs
            return ds.to_zarr(outfile, **kwargs)

        raise ValueError(f"File format '{format}' not supported.")

    def add_metadata(
        self,
        ds: xr.Dataset,
        **metadata_kwargs: Any,
    ) -> xr.Dataset:
        """Set some dataset attributes with information on how it was created.

        Wrapper around :meth:`get_metadata`.
        Attributes already present will not be overwritten.

        Parameters
        ----------
        ds
            Dataset to add global attributes to. This is **not** done in-place.
        metadata_kwargs
            Passed to the :attr:`~.WriterAbstract.metadata_generator`. See
            :class:`.MetadataOptions` for available options.
        """
        meta = self.get_metadata(**metadata_kwargs)
        return self._add_metadata(ds, meta)

    def _add_metadata(self, ds: xr.Dataset, metadata: Mapping) -> xr.Dataset:
        # copy
        metadata = dict(metadata)
        # Do not overwrite attributes.
        for k in set(ds.attrs.keys()) & set(metadata.keys()):
            metadata.pop(k)
        return ds.assign_attrs(**metadata)

    def send_calls_together(
        self,
        calls: Sequence[CallXr],
        client: Client,
        chop: int | None = None,
        format: Literal["nc", "zarr", None] = None,
        **kwargs: Any,
    ) -> None:
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
            :attr:`to_netcdf_kwargs` or :attr:`to_zarr_kwargs`.
        """
        import distributed

        self.check_overwriting_calls(calls)
        self.check_directories(calls)

        ncalls = len(calls)
        if chop is None:
            chop = ncalls

        slices = cut_in_slices(ncalls, chop)
        log.info("%d total calls in %d groups.", ncalls, len(slices))

        kwargs = self.to_netcdf_kwargs | kwargs
        kwargs["compute"] = False

        for slc in slices:
            log.info("\tslice %s", slc)

            grouped_calls = calls[slc]
            delayed = [self.send_single_call(c, **kwargs) for c in grouped_calls]

            # Futures are deleted as soon as they go out of scope. They do not pile up
            # but we still return only when all are completed.
            for future in distributed.as_completed(client.compute(delayed)):
                log.debug("\t\tfuture completed: %s", future)

    def write(
        self,
        data: xr.Dataset | Sequence[xr.Dataset],
        target: str | Sequence[str] | None = None,
        metadata_kwargs: Mapping[str, Any] | None = None,
        client: Client | None = None,
        **kwargs: Any,
    ) -> Any:
        """Write datasets to multiple targets.

        Each dataset is written to its corresponding target (filename or store
        location). Directories will automatically be created if necessary. Metadata is
        added to the dataset.

        Parameters
        ----------
        data
            Dataset or Sequence of datasets to write.
        target
            If None (default), target location(s) are automatically obtained via
            :meth:`.DataInterface.get_source`.
        client:
            Dask :class:`distributed.Client` instance. If present multiple write calls
            will be send in parallel. See :meth:`send_calls_together` for details.
            If left to None, the write calls will be sent serially.
        metadata_kwargs
            Passed to the :attr:`~.WriterAbstract.metadata_generator`. See
            :class:`.MetadataOptions` for available options.
        kwargs
            Passed to the function that writes to disk
            (:meth:`xarray.Dataset.to_netcdf` or :meth:`xarray.Dataset.to_zarr`).
        """
        if target is None:
            target = self.di.get_source()
        if isinstance(target, str | os.PathLike):
            target = [target]

        if isinstance(data, xr.Dataset):
            data = [data]

        if metadata_kwargs is None:
            metadata_kwargs = {}
        data = [self.add_metadata(d, **metadata_kwargs) for d in data]

        if len(target) != len(data):
            raise IndexError(
                f"Number of writing targets ({len(target)}) differing from "
                f"number of datasets ({len(data)})"
            )
        calls = list(zip(target, data))

        self.check_directories(calls)
        self.check_overwriting_calls(calls)
        if len(calls) > 1 and client is not None:
            return self.send_calls_together(calls, client, **kwargs)
        return self.send_calls(calls, **kwargs)


class XarraySplitWriter(SplitWriterMixin, XarrayWriter):
    """Writer for Xarray datasets in multiple files automatically.

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
        squeeze: bool | str | Mapping[Hashable, bool | str] = False,
        client: Client | None = None,
        chop: int | None = None,
        metadata_kwargs: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Delayed | xr.backends.ZarrStore | None] | None:
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
            Cannot be used here. Use :class:`.XarrayWriter` instead.
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
        metadata_kwargs
            Passed to the :attr:`~.WriterAbstract.metadata_generator`. See
            :class:`.MetadataOptions` for available options.
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

        self.check_directories(calls)
        self.check_overwriting_calls(calls)

        if metadata_kwargs is None:
            metadata_kwargs = {}
        metadata = self.get_metadata(**metadata_kwargs)
        calls = [(f, self._add_metadata(ds, metadata)) for f, ds in calls]

        if client is not None:
            self.send_calls_together(calls, client, chop=chop, **kwargs)
            return None
        return self.send_calls(calls, **kwargs)

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
        unfixed = self.unfixed()
        # Only keep time related unfixed
        unfixed &= set(self.time_intervals_groups)

        # not time dimension or no unfixed params in filename pattern
        if "time" not in ds.dims or not unfixed:
            log.debug("Not splitting by time.")
            return [ds]

        # user asked to not resample
        if not time_freq:
            return [ds.isel(time=[i]) for i in range(ds.time.size)]

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

        # Check if dataset frequency is equal to split frequency (no need to resample)
        if ds.time.size >= 3:
            infreq = xr.infer_freq(ds.time)
            if infreq is not None and infreq == freq:
                log.debug(
                    "Resampling frequency is equal to that of dataset. "
                    "Will not resample."
                )
                return [ds.isel(time=[i]) for i in range(ds.time.size)]

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
        unfixed = self.unfixed()
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
        datasets: Sequence[xr.Dataset],
        squeeze: bool | str | Mapping[Hashable, bool | str] = False,
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
        unfixed = self.unfixed()
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
                    val = self.parameters.direct[dim]
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

            calls.append((outfile, ds))

        return calls
