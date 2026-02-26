"""Test source modules."""

from pathlib import Path

import pandas as pd
import pytest

from neba.data.interface import DataInterface
from neba.data.params import ParametersDict
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

    def test_no_select(self):
        SourceA = get_simple_source("SourceA", ["a", "b", "c"])
        SourceB = get_simple_source("SourceB", ["b", "c", "d", "e"])
        mix_cls = SourceIntersection.create([SourceA, SourceB])
        mix = mix_cls()
        with pytest.raises(ValueError):
            mix.select()

        def select(mod, *args, **kwargs):
            return "SourceA"

        mix.set_select(select)
        assert isinstance(mix.select(), SourceA)

    def test_select_unbound(self):
        """Select function is defined outside of interface."""

        class SourceA(SimpleSource):
            source_loc = "a"

            def get_filename(self, **fixes):
                param = self.parameters["param"]
                if "param" in fixes:
                    param = fixes["param"]
                return f"file_a_{param}"

        class SourceB(SimpleSource):
            source_loc = "b"

            def get_filename(self, **fixes):
                param = self.parameters["param"]
                if "param" in fixes:
                    param = fixes["param"]
                return f"file_b_{param}"

        def select(module, **kwargs):
            return kwargs.get("selected", module.parameters["selected"])

        class DataInterfaceMix(DataInterface):
            Parameters = ParametersDict
            Source = SourceUnion.create([SourceA, SourceB], select_func=select)

        di = DataInterfaceMix(param=0, selected="SourceA")

        assert di.source.apply_select("get_filename") == "file_a_0"

    def get_interface(self):
        class DataInterfaceMix(DataInterface):
            Parameters = ParametersDict

            class SourceA(SimpleSource):
                source_loc = "a"

                def get_filename(self, **fixes):
                    param = fixes.get("param", self.parameters["param"])
                    return f"file_a_{param}"

            class SourceB(SimpleSource):
                source_loc = "b"

                def get_filename(self, **fixes):
                    param = fixes.get("param", self.parameters["param"])
                    return f"file_b_{param}"

            @staticmethod
            def select(module, **kwargs):
                return kwargs.get("selected", module.parameters["selected"])

            Source = SourceUnion.create([SourceA, SourceB], select_func=select)

        return DataInterfaceMix

    def test_select_bound(self):
        """Select is defined as static method."""
        di = self.get_interface()(param=0, selected="SourceA")
        assert di.source.apply_select("get_filename") == "file_a_0"

    def test_file_select(self):
        di = self.get_interface()(param=0, selected="SourceA")

        assert di.source.apply_select("get_filename") == "file_a_0"

        di.parameters["param"] = 1
        di.parameters["selected"] = "SourceB"
        assert di.source.apply_select("get_filename") == "file_b_1"
        assert di.source.apply_select("get_filename", param=2) == "file_b_2"

        # take precedence over interface param
        assert (
            di.source.apply_select(
                "get_filename", select={"selected": "SourceA"}, param=2
            )
            == "file_a_2"
        )

    def test_apply(self):
        di = self.get_interface()(param=0, selected="SourceA")
        assert di.source.apply("get_filename", all=True, param=1) == [
            "file_a_1",
            "file_b_1",
        ]

        assert di.source.apply("get_filename", all=False, param=1) == "file_a_1"

    def test_automatic_dispatch(self):
        di = self.get_interface()(param=0, selected="SourceA")

        assert di.source.get_filename() == "file_a_0"
        di.parameters["selected"] = "SourceB"
        assert di.source.get_filename() == "file_b_0"

        # disabled
        di.source._auto_dispatch_getattr = False
        with pytest.raises(AttributeError):
            di.source.get_filename()

        # attribute does not exist in base classes
        with pytest.raises(AttributeError):
            di.source.unknown_attribute()

        # exception in selection function: no infinie recursion
        def select(mod, **kwargs):
            raise ValueError

        di.source.set_select(select)
        with pytest.raises(ValueError):
            di.source.select()
        with pytest.raises(AttributeError):
            di.source.get_filename()

    def test_bad_select(self):
        di = self.get_interface()

        def select(mod, **kwargs):
            return "NonExistentBaseModule"

        with pytest.raises(AttributeError):
            di.source.select()


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
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

            class Source(GlobSource):
                # here we test root_directory as a simple str
                def get_root_directory(self):
                    return str(tmpdir)

                def get_glob_pattern(self):
                    return f"*/{self.parameters['var']}_*.nc"

        ref_filenames = setup_multiple_files(tmpdir, var="A")

        di = MyDataInterface(var="A")
        assert di.get_source() == ref_filenames

        # test relative
        assert di.get_source(relative=True) == [
            f.removeprefix(str(tmpdir) + "/") for f in ref_filenames
        ]

        # check files cached
        assert di.source.cache["datafiles"] == ref_filenames

        # check void cache
        di.parameters["var"] = "B"
        assert "datafiles" not in di.source.cache
        assert len(di.get_source()) == 0


class TestFileFinder:
    def setup_interface(self, tmpdir) -> type[DataInterface]:
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

            class Source(FileFinderSource):
                # here we test root_directory as a list
                def get_root_directory(self):
                    return [str(tmpdir), "subdir"]

                def get_filename_pattern(self):
                    var = self.parameters["var"]
                    return f"%(Y)/{var}_%(Y)%(m)%(d)_%(param:fmt=02d).nc"

        return MyDataInterface

    def test_get_source(self, tmpdir):
        ref_filenames = setup_multiple_files(tmpdir / "subdir", var="A")

        di = self.setup_interface(tmpdir)(var="A")
        assert di.get_source() == ref_filenames

        # test relative
        assert di.get_source(relative=True) == [
            f.removeprefix(str(tmpdir / "subdir") + "/") for f in ref_filenames
        ]

        # check files cached
        assert di.source.cache["datafiles"] == ref_filenames

        # check void cache
        di.parameters["var"] = "B"
        assert "datafiles" not in di.source.cache
        assert len(di.get_source()) == 0

    def test_fixes(self, tmpdir):
        ref_filenames = setup_multiple_files(tmpdir / "subdir", var="A")

        di = self.setup_interface(tmpdir)(var="A", Y="2010")

        assert di.get_source() == ref_filenames[:36]
        assert di.source.fixable == {"Y", "m", "d", "param"}
        assert di.source.unfixed == ["m", "d", "param"]

        di.parameters["d"] = 1
        di.parameters["m"] = [1, 2]

        assert di.source.unfixed == ["m", "param"]
        assert di.get_source() == ref_filenames[:6]
