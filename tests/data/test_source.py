"""Test source modules."""

import pytest

from neba.data.dataset import Dataset
from neba.data.params import ParamsManagerDict
from neba.data.source import SimpleSource, SourceIntersection, SourceUnion


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


# TODO: filefinder
# test some of the properties, like unfixed?
