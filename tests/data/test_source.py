"""Test source modules."""

from pathlib import Path

import pandas as pd
import pytest

from neba.data.dataset import Dataset
from neba.data.params import ParamsManagerDict
from neba.data.source import (
    FileFinderSource,
    GlobSource,
    SimpleSource,
    SourceIntersection,
    SourceUnion,
)


def get_simple_source(name, files: list[str]):
    return type(name, (SimpleSource,), {"source_loc": files})


class TestModuleMix:
    def test_wrong_name(self):
        with pytest.raises(KeyError):
            mix_cls = SourceUnion.create(
                [
                    get_simple_source("Source", ["a", "b", "c"]),
                    get_simple_source("Source", ["b", "c", "d", "e"]),
                ]
            )
            mix_cls()

    def test_union(self):
        mix_cls = SourceUnion.create(
            [
                get_simple_source("SourceA", ["a", "b", "c"]),
                get_simple_source("SourceB", ["b", "c", "d", "e"]),
            ]
        )
        mix = mix_cls()
        assert mix.get_source() == ["a", "b", "c", "d", "e"]

    def test_intersection(self):
        mix_cls = SourceIntersection.create(
            [
                get_simple_source("SourceA", ["a", "b", "c"]),
                get_simple_source("SourceB", ["b", "c", "d", "e"]),
            ]
        )
        mix = mix_cls()
        assert mix.get_source() == ["b", "c"]

    def test_file_select(self):
        class SourceA(SimpleSource):
            source_loc = "a"

            def get_filename(self, **fixes):
                param = self.params["param"]
                if "param" in fixes:
                    param = fixes["param"]
                return f"file_a_{param}"

        class SourceB(SimpleSource):
            source_loc = "b"

            def get_filename(self, **fixes):
                param = self.params["param"]
                if "param" in fixes:
                    param = fixes["param"]
                return f"file_b_{param}"

        def select(module, **kwargs):
            return kwargs.get("selected", module.params["selected"])

        class DatasetMix(Dataset):
            ParamsManager = ParamsManagerDict
            Source = SourceUnion.create([SourceA, SourceB], select_func=select)

        dm = DatasetMix(param=0, selected="SourceA")

        assert dm.source.apply_select("get_filename") == "file_a_0"

        dm.params["param"] = 1
        dm.params["selected"] = "SourceB"
        assert dm.source.apply_select("get_filename") == "file_b_1"
        assert dm.source.apply_select("get_filename", param=2) == "file_b_2"

        # take precedence over dataset param
        assert (
            dm.source.apply_select(
                "get_filename", select={"selected": "SourceA"}, param=2
            )
            == "file_a_2"
        )

        # automatic dispatch
        assert dm.source.get_filename() == "file_b_1"


def setup_multiple_files(tmpdir, var: str = "A") -> list[str]:
    """Create empty files in tmpdir.

    Pattern is <year>/<var>_<year><month><day>_<param>.nc
    """
    dates = pd.date_range(start="20100101", end="20121231", freq="1MS")
    params = [1, 2, 3]

    filenames = []
    for date in dates:
        for param in params:
            filename = (
                f"{date.year:04d}/"
                f"{var}_{date.year:04d}{date.month:02d}{date.day:02d}"
                f"_{param:02d}.nc"
            )
            new_file = Path(tmpdir) / filename
            if not new_file.parent.exists():
                new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.touch()
            filenames.append(str(new_file))

    return filenames


class TestGlob:
    def test_get_source(self, tmpdir):
        class MyDataset(Dataset):
            ParamsManager = ParamsManagerDict

            class Source(GlobSource):
                def get_root_directory(self):
                    return str(tmpdir)

                def get_glob_pattern(self):
                    return f"*/{self.params['var']}_*.nc"

        ref_filenames = setup_multiple_files(tmpdir, var="A")

        dm = MyDataset(var="A")
        assert dm.get_source() == ref_filenames

        # check files cached
        assert dm.source.cache["datafiles"] == ref_filenames

        # check void cache
        dm.params["var"] = "B"
        assert "datafiles" not in dm.source.cache
        assert len(dm.get_source()) == 0


class TestFileFinder:
    def setup_dataset(self, tmpdir) -> type[Dataset]:
        class MyDataset(Dataset):
            ParamsManager = ParamsManagerDict

            class Source(FileFinderSource):
                def get_root_directory(self):
                    return str(tmpdir)

                def get_filename_pattern(self):
                    return f"%(Y)/{self.params['var']}_%(Y)%(m)%(d)_%(param:fmt=02d).nc"

        return MyDataset

    def test_get_source(self, tmpdir):
        ref_filenames = setup_multiple_files(tmpdir, var="A")

        dm = self.setup_dataset(tmpdir)(var="A")
        assert dm.get_source() == ref_filenames

        # check files cached
        assert dm.source.cache["datafiles"] == ref_filenames

        # check void cache
        dm.params["var"] = "B"
        assert "datafiles" not in dm.source.cache
        assert len(dm.get_source()) == 0

    def test_fixes(self, tmpdir):
        ref_filenames = setup_multiple_files(tmpdir, var="A")

        dm = self.setup_dataset(tmpdir)(var="A", Y="2010")

        assert dm.get_source() == ref_filenames[:36]
        assert dm.source.fixable == {"Y", "m", "d", "param"}
        assert dm.source.unfixed == ["m", "d", "param"]

        dm.params["d"] = 1
        dm.params["m"] = [1, 2]

        assert dm.source.unfixed == ["m", "param"]
        assert dm.get_source() == ref_filenames[:6]
