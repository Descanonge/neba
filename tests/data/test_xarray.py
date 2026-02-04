"""Test Xarray loading / writing."""

from os import path

import numpy as np
import pandas as pd
import xarray as xr
from xarray.testing import assert_equal

from data_assistant.data import Dataset, FileFinderSource, ParamsManagerDict
from data_assistant.data.xarray import XarrayLoader, XarraySplitWriter, XarrayWriter
from tests.conftest import todo


class XarrayDataset(Dataset):
    ParamsManager = ParamsManagerDict
    Loader = XarrayLoader
    Writer = XarrayWriter


class TestLoader:
    def setup_single_file(self, tmpdir, fmt: str) -> tuple[xr.Dataset, str]:
        ref = xr.Dataset(
            {"test": xr.DataArray(np.arange(4), coords={"x": range(4)}, dims=["x"])}
        )

        if fmt == "netcdf":
            filename = tmpdir / "test_dataset.nc"
            ref.to_netcdf(filename)
        elif fmt == "zarr":
            filename = tmpdir / "test_dataset.zarr"
            ref.to_zarr(filename)
        else:
            raise KeyError

        return ref, filename

    def test_open_dataset(self, tmpdir):
        ref, filename = self.setup_single_file(tmpdir, "netcdf")

        dm = XarrayDataset()
        loaded = dm.get_data(source=filename)

        assert_equal(loaded, ref)

    def test_open_dataset_zarr(self, tmpdir):
        class XarrayDataset(Dataset):
            ParamsManager = ParamsManagerDict
            Loader = XarrayLoader

        ref, filename = self.setup_single_file(tmpdir, "zarr")

        dm = XarrayDataset()
        loaded = dm.get_data(source=filename)

        assert_equal(loaded, ref)

    def test_postprocess(self, tmpdir):
        ref, filename = self.setup_single_file(tmpdir, "netcdf")

        class XarrayDataset(Dataset):
            ParamsManager = ParamsManagerDict

            class Loader(XarrayLoader):
                def postprocess(self, data):
                    data["test"] += 2
                    return data

        dm = XarrayDataset()

        loaded = dm.get_data(source=filename, ignore_postprocess=True)
        assert_equal(loaded, ref)

        ref["test"] += 2
        loaded = dm.get_data(source=filename)
        assert_equal(loaded, ref)

    def setup_multifile(
        self, tmpdir, concatenate: bool = True
    ) -> tuple[xr.Dataset, list[str]]:
        data = np.arange(12).reshape(3, 4)

        ref = xr.Dataset(
            {
                "test": xr.DataArray(
                    data, coords={"time": range(3), "x": range(4)}, dims=["time", "x"]
                )
            }
        )

        filenames = [tmpdir / f"test_mf_dataset_{i}.nc" for i in range(ref.time.size)]
        for i, filename in enumerate(filenames):
            ref.isel(time=[i] if concatenate else i).to_netcdf(filename)

        return ref, filenames

    def test_open_mfdataset(self, tmpdir):
        ref, filenames = self.setup_multifile(tmpdir)

        dm = XarrayDataset()
        loaded = dm.get_data(source=filenames)

        assert_equal(loaded, ref)

    def test_preprocess_filefinder(self, tmpdir):
        """Use FileFinderSource to add dimension for concatenation."""
        ref, filenames = self.setup_multifile(tmpdir, concatenate=False)

        class XarrayDataset(Dataset):
            ParamsManager = ParamsManagerDict

            class Source(FileFinderSource):
                def get_root_directory(self):
                    return str(tmpdir)

                def get_filename_pattern(self):
                    return "test_mf_dataset_%(time:fmt=d).nc"

            class Loader(XarrayLoader):
                OPEN_MFDATASET_KWARGS = {"preprocess": True}

                def preprocess(self):
                    finder = self.dm.source.filefinder

                    def func(ds: xr.Dataset) -> xr.Dataset:
                        filename = ds.encoding["source"]
                        matches = finder.get_matches(filename, relative=False)
                        ds = ds.expand_dims(time=[matches["time"]])
                        return ds

                    return func

        dm = XarrayDataset()
        loaded = dm.get_data()

        assert_equal(loaded, ref)


class TestWriter:
    def test_single_file(self, tmpdir):
        ref = xr.Dataset(
            {"test": xr.DataArray(np.arange(4), coords={"x": range(4)}, dims=["x"])}
        )
        filename = tmpdir / "test_dataset.nc"

        dm = XarrayDataset()
        dm.write(ref, target=filename)

        written = xr.open_dataset(filename)

        assert_equal(written, ref)

    @todo
    def test_zarr(self, tmpdir):
        pass

    def test_metadata(self, tmpdir):
        ref = xr.Dataset(
            {"test": xr.DataArray(np.arange(4), coords={"x": range(4)}, dims=["x"])}
        )
        filename = tmpdir / "test_dataset.nc"

        dm = XarrayDataset(a=0)
        dm.write(ref, target=filename)

        written = xr.open_dataset(filename)

        assert written.attrs["written_as_dataset"] == "XarrayDataset"
        assert written.attrs["created_with_params"] == '{"a": 0}'
        for attr in ["created_by", "created_on", "created_at_commit"]:
            assert attr in written.attrs

    def setup_multifile(self, tmpdir) -> tuple[xr.Dataset, list[xr.Dataset], list[str]]:
        data = np.arange(12).reshape(3, 4)

        ref = xr.Dataset(
            {
                "test": xr.DataArray(
                    data, coords={"time": range(3), "x": range(4)}, dims=["time", "x"]
                )
            }
        )

        filenames = [tmpdir / f"test_mf_dataset_{i}.nc" for i in range(ref.time.size)]
        ref_split = [ref.isel(time=[i]) for i in range(ref.time.size)]
        return ref, ref_split, filenames

    def test_multifile_serial(self, tmpdir):
        _, ref_split, filenames = self.setup_multifile(tmpdir)

        dm = XarrayDataset()
        dm.write(ref_split, target=filenames)

        written = [xr.open_dataset(filename) for filename in filenames]

        for r, w in zip(ref_split, written, strict=True):
            assert_equal(r, w)

    @todo
    def test_multifile_together(self):
        assert 0


class TestSplitWriter:
    def get_data(self, freq="1D") -> xr.Dataset:
        data = np.arange(24).reshape(4, 2, 3)

        time = pd.date_range(start="2000-01-01", periods=4, freq=freq)
        ref = xr.Dataset(
            {
                "test": xr.DataArray(
                    data,
                    coords={"time": time, "y": range(2), "x": range(3)},
                    dims=["time", "y", "x"],
                )
            }
        )
        return ref

    def test_daily(self, tmpdir):
        class XarrayDataset(Dataset):
            ParamsManager = ParamsManagerDict
            Writer = XarraySplitWriter

            class Source(FileFinderSource):
                def get_root_directory(self):
                    return tmpdir

                def get_filename_pattern(self):
                    return "%(Y)-%(m)-%(d)_%(y:fmt=02d).nc"

        ref = self.get_data("1D")
        dm = XarrayDataset()
        dm.write(ref)

        for date in ["01-01", "01-02", "01-03", "01-04"]:
            for y in range(2):
                assert path.isfile(str(tmpdir / f"2000-{date}_{y:02d}.nc"))

    def test_long_freq(self, tmpdir):
        class XarrayDataset(Dataset):
            ParamsManager = ParamsManagerDict
            Writer = XarraySplitWriter

            class Source(FileFinderSource):
                def get_root_directory(self):
                    return tmpdir

                def get_filename_pattern(self):
                    return "%(Y)-%(m)-%(d)_%(y:fmt=02d).nc"

        ref = self.get_data("40D")
        dm = XarrayDataset()
        dm.write(ref)

        for date in ["01-01", "02-10", "03-21", "04-30"]:
            for y in range(2):
                assert path.isfile(str(tmpdir / f"2000-{date}_{y:02d}.nc"))

    def test_monthly_file(self, tmpdir):
        class XarrayDataset(Dataset):
            ParamsManager = ParamsManagerDict
            Writer = XarraySplitWriter

            class Source(FileFinderSource):
                def get_root_directory(self):
                    return tmpdir

                def get_filename_pattern(self):
                    return "%(Y)-%(m).nc"

        data = np.arange(24).reshape(12, 2)

        time = pd.date_range(start="2000-01-01", periods=12, freq="10D")
        ref = xr.Dataset(
            {
                "test": xr.DataArray(
                    data,
                    coords={"time": time, "x": range(2)},
                    dims=["time", "x"],
                )
            }
        )

        dm = XarrayDataset()
        dm.write(ref)

        for month in range(4):
            assert path.isfile(str(tmpdir / f"2000-{month+1:02d}.nc"))

        # check values
        splits = dm.writer.split_by_time(ref)
        assert len(splits) == 4
        assert_equal(splits[0].time, ref.time[:4])
        assert_equal(splits[1].time, ref.time[4:6])
        assert_equal(splits[2].time, ref.time[6:10])
        assert_equal(splits[3].time, ref.time[10:])
