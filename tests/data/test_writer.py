"""Test common Writer features."""

import os

import pytest

from neba.data import DataInterface, ParametersDict
from neba.data.writer import MetadataGenerator, WriterAbstract, method


def test_check_directories(tmpdir):
    (tmpdir / "a").mkdir()

    calls = [(str(tmpdir / "a" / "b" / "file.txt"), None)]

    writer = WriterAbstract()
    writer.check_directories(calls)

    assert (tmpdir / "a" / "b").exists()


def test_check_overwriting_calls():
    writer = WriterAbstract()

    writer.check_overwriting_calls([("a/b/0", None), ("a/b/1", None), ("a/0", None)])

    with pytest.raises(ValueError):
        writer.check_overwriting_calls(
            [("a/b/0", None), ("a/b/1", None), ("a/b/0", None)]
        )


class TestMetadata:
    METH_BASIC = [
        "written_with_interface",
        "creation_time",
        "creation_hostname",
        "creation_script",
    ]
    METH_PARAMS = ["creation_params"]
    METH_GIT = ["creation_commit", "creation_diff"]

    def get_interface(self, *args, **kwargs) -> DataInterface:
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

        return MyDataInterface(*args, **kwargs)

    def test_methods_selection(self):

        di = self.get_interface()
        metadata = di.writer.get_metadata()

        # git will fail on github CI for some reason
        for key in self.METH_BASIC + self.METH_PARAMS:
            assert key in metadata

        # Test group skip
        assert (
            di.writer.metadata_generator(None, add_git_info=False).get_methods()
            == self.METH_BASIC + self.METH_PARAMS
        )

        assert (
            di.writer.metadata_generator(None, add_params=False).get_methods()
            == self.METH_BASIC + self.METH_GIT
        )

        metadata = di.writer.get_metadata(add_params=False, add_git_info=False)
        assert list(metadata.keys()) == self.METH_BASIC

        # Test manually specifying methods (in different order)
        methods = ["creation_hostname", "written_with_interface", "creation_params"]
        metadata = di.writer.get_metadata(methods=methods)
        assert list(metadata.keys()) == methods

        with pytest.raises(AttributeError):
            di.writer.get_metadata(methods=["creation_hostname", "unknown_method"])

    def test_generator_subclass(self):
        class MyGenerator(MetadataGenerator):
            @method
            def simple(self):
                return 0

            @method(items=["a", "b"])
            def multiple(self):
                return {"a": 0, "b": 1}

            @method(items=["b"])
            def last(self):
                return {"b": 5}

        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

            class Writer(WriterAbstract):
                metadata_generator = MyGenerator

        di = MyDataInterface()
        metadata = di.writer.get_metadata(add_git_info=False)

        assert list(metadata.keys()) == self.METH_BASIC + self.METH_PARAMS + [
            "simple",
            "a",
            "b",
        ]

        assert metadata["simple"] == 0
        assert metadata["a"] == 0
        assert metadata["b"] == 5

    def test_renaming(self):
        class MyGenerator(MetadataGenerator):
            @method
            def simple(self):
                return 0

            @method(items=["a", "b"])
            def multiple(self):
                return {"a": 0, "b": 1}

            @method(name_mapping=dict(from_decorator="renamed_from_decorator"))
            def from_decorator(self):
                return 0

        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

            class Writer(WriterAbstract):
                metadata_generator = MyGenerator

        di = MyDataInterface()
        MyGenerator.simple.rename("simple_rename")
        MyGenerator.multiple.rename(a="a_rename")
        metadata = di.writer.get_metadata(
            methods=["simple", "multiple", "from_decorator"]
        )
        assert metadata == dict(
            simple_rename=0, a_rename=0, b=1, renamed_from_decorator=0
        )

        with pytest.raises(TypeError):
            MyGenerator.multiple.rename("simple_renaming")

        with pytest.raises(KeyError):
            MyGenerator.multiple.rename(wrong="a_rename")

    def test_parameters(self):
        params = dict(a=0, b=1)
        di = self.get_interface(params)
        metadata = di.writer.get_metadata(params_str=False)
        assert metadata["creation_params"] == params

        metadata = di.writer.get_metadata()
        assert metadata["creation_params"] == '{"a": 0, "b": 1}'

    def test_script_filename(self):
        di = self.get_interface()
        metadata = di.writer.get_metadata(
            creation_script="a", methods=["creation_script"]
        )
        assert metadata["creation_script"] == "a"

        # Pytest messes with getting filename (similarly to IPython)
        # not sure how to test it properly

    def test_git(self):
        di = self.get_interface()
        metadata = di.writer.get_metadata(creation_script=".")
        assert "creation_commit" in metadata

        if (commit := os.environ.get("GITHUB_SHA")) is not None:
            assert metadata["creation_commit"] == commit

    def test_none(self):
        """Method that returns None is not added to metadata."""

        class MyGenerator(MetadataGenerator):
            @method
            def none(self):
                return None

        gen = MyGenerator(None, methods=["none"])
        assert gen.generate() == dict()
