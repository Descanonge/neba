"""Test main dataset and modules features."""

import pytest

from neba.data import (
    LoaderAbstract,
    ParametersAbstract,
    ParametersDict,
    SourceAbstract,
    WriterAbstract,
)
from neba.data.dataset import Dataset
from neba.data.module import ModuleMix


def test_abstract_dataset():
    """Simple sanity test."""

    class TestDataset(Dataset):
        pass

    assert issubclass(TestDataset.Parameters, ParametersAbstract)
    assert issubclass(TestDataset.Source, SourceAbstract)
    assert issubclass(TestDataset.Loader, LoaderAbstract)
    assert issubclass(TestDataset.Writer, WriterAbstract)

    dm = TestDataset()
    assert isinstance(dm.parameters, ParametersAbstract)
    assert isinstance(dm.source, SourceAbstract)
    assert isinstance(dm.loader, LoaderAbstract)
    assert isinstance(dm.writer, WriterAbstract)


def test_dataset_custom():
    """Test module definition."""

    # external module definition
    class P(ParametersAbstract):
        pass

    class S(SourceAbstract):
        pass

    class TestDataset(Dataset):
        Parameters = P
        Source = S

        # internal definition
        class Loader(LoaderAbstract):
            pass

        class Writer(WriterAbstract):
            pass

    dm = TestDataset()
    assert isinstance(dm.parameters, P)
    assert isinstance(dm.source, S)
    assert isinstance(dm.loader, TestDataset.Loader)
    assert isinstance(dm.writer, TestDataset.Writer)


def test_instantiate_order():
    """Check the instantiation order of modules is the one frome _modules_attributes."""
    order = []

    def init(self, *args, **kwargs):
        order.append(self.__class__.__name__)

    class TestDataset(Dataset):
        Parameters = type("P", (ParametersAbstract,), {"__init__": init})
        Source = type("S", (SourceAbstract,), {"__init__": init})
        Loader = type("L", (LoaderAbstract,), {"__init__": init})
        Writer = type("W", (WriterAbstract,), {"__init__": init})

    TestDataset()
    assert order == ["P", "S", "L", "W"]


def test_module_error():
    """Test module instantiation raises (or not)."""

    class TestDataset(Dataset):
        class Source(SourceAbstract):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                raise ValueError

    TestDataset.Source._allow_instantiation_failure = False
    with pytest.raises(ValueError):
        TestDataset()

    TestDataset.Source._allow_instantiation_failure = True
    assert not hasattr(TestDataset(), "source")


def test_parent_dataset_access():
    """Test backref to parent dataset."""

    class TestDataset(Dataset):
        pass

    dm = TestDataset()
    for mod in dm._modules.values():
        assert mod.dm is dm


def test_module_setup():
    """Test all modules are setup, and in order."""
    order = []

    def setup(self, *args, **kwargs):
        order.append(self.__class__.__name__)

    class TestDataset(Dataset):
        Parameters = type("P", (ParametersAbstract,), {"setup": setup})
        Source = type("S", (SourceAbstract,), {"setup": setup})
        Loader = type("L", (LoaderAbstract,), {"setup": setup})
        Writer = type("W", (WriterAbstract,), {"setup": setup})

    dm = TestDataset()
    assert order == ["P", "S", "L", "W"]
    for mod in dm._modules.values():
        assert mod._is_setup is True


def test_module_setup_ancestors():
    """Check all ancestors are setup."""
    is_setup = set()

    class SourceA(SourceAbstract):
        def setup(self):
            is_setup.add("A")
            super().setup()

    class SourceC(SourceAbstract):
        def setup(self):
            is_setup.add("C")
            super().setup()

    class SourceB(SourceC):
        def setup(self):
            is_setup.add("B")
            super().setup()

    class TestDataset(Dataset):
        class Source(SourceA, SourceB):
            def setup(self):
                super().setup()

    TestDataset()
    assert is_setup == {"A", "B", "C"}


def test_str():
    class OnlyID(Dataset):
        ID = "MyID"

    class OnlyShortname(Dataset):
        SHORTNAME = "MySHORTNAME"

    class Both(Dataset):
        ID = "MyID"
        SHORTNAME = "MySHORTNAME"

    class Neither(Dataset):
        pass

    assert str(OnlyID()) == "MyID (OnlyID)"
    assert str(OnlyShortname()) == "MySHORTNAME (OnlyShortname)"
    assert str(Both()) == "MySHORTNAME:MyID (Both)"
    assert str(Neither()) == "Neither"


def test_reset_callbacks():
    class TestDataset(Dataset):
        called = False
        called_bis = False

    def callback(dm, **kwargs):
        dm.called = True

    def callback_bis(dm, **kwargs):
        dm.called_bis = True

    dm = TestDataset()
    dm.register_callback("test_callback", callback)
    dm.register_callback("test_callback_bis", callback_bis)

    with pytest.raises(KeyError):
        dm.register_callback("test_callback", callback)

    assert not dm.called
    assert not dm.called_bis
    dm.trigger_callbacks()
    assert dm.called
    assert dm.called_bis

    dm.called = False
    dm.called_bis = False

    dm.trigger_callbacks(False)
    assert not dm.called
    assert not dm.called_bis

    dm.trigger_callbacks(["test_callback_bis"])
    assert not dm.called
    assert dm.called_bis


def test_get_data_sets():
    class MyDataset(Dataset):
        Parameters = ParametersDict

        # just return a copy of parameters as data
        def get_data(self, **kwargs):
            return dict(self.parameters.direct)

    dm = MyDataset(a=0, b=0)

    params_maps = [
        {"a": 0, "b": 0, "c": 0},
        {"a": 1, "b": 0, "c": 1},
        {"a": 2, "b": 3, "c": 4},
    ]
    data = dm.get_data_sets(params_maps)
    assert data == params_maps
    assert dm.parameters.direct == dict(a=0, b=0)

    data = dm.get_data_sets(
        params_sets=[
            ["a", "b", "c"],
            [0, 0, 0],
            [1, 0, 1],
            [2, 3, 4],
        ]
    )
    assert data == params_maps
    assert dm.parameters.direct == dict(a=0, b=0)


class TestModuleMix:
    def test_setup(self):
        is_setup = set()

        class SourceA(SourceAbstract):
            def setup(self):
                is_setup.add("A")
                super().setup()

        class SourceC(SourceAbstract):
            def setup(self):
                is_setup.add("C")
                super().setup()

        class SourceB(SourceC):
            def setup(self):
                is_setup.add("B")
                super().setup()

        class TestDataset(Dataset):
            Source = ModuleMix.create([SourceA, SourceB])

        TestDataset()
        assert is_setup == {"A", "B", "C"}
