"""Test main dataset and modules features."""

import pytest

from data_assistant.data import (
    LoaderAbstract,
    ParamsManagerAbstract,
    SourceAbstract,
    WriterAbstract,
)
from data_assistant.data.dataset import Dataset
from data_assistant.data.module import ModuleMix


def test_abstract_dataset():
    """Simple sanity test."""

    class TestDataset(Dataset):
        pass

    assert issubclass(TestDataset.Params, ParamsManagerAbstract)
    assert issubclass(TestDataset.Source, SourceAbstract)
    assert issubclass(TestDataset.Loader, LoaderAbstract)
    assert issubclass(TestDataset.Writer, WriterAbstract)

    dm = TestDataset()
    assert isinstance(dm.params_manager, ParamsManagerAbstract)
    assert isinstance(dm.source, SourceAbstract)
    assert isinstance(dm.loader, LoaderAbstract)
    assert isinstance(dm.writer, WriterAbstract)


def test_dataset_custom():
    """Test module definition."""

    # external module definition
    class P(ParamsManagerAbstract):
        pass

    class S(SourceAbstract):
        pass

    class TestDataset(Dataset):
        Params = P
        Source = S

        # internal definition
        class Loader(LoaderAbstract):
            pass

        class Writer(WriterAbstract):
            pass

    dm = TestDataset()
    assert isinstance(dm.params_manager, P)
    assert isinstance(dm.source, S)
    assert isinstance(dm.loader, TestDataset.Loader)
    assert isinstance(dm.writer, TestDataset.Writer)


def test_instantiate_order():
    """Check the instantiation order of modules is the one frome _modules_attributes."""
    order = []

    def init(self, *args, **kwargs):
        order.append(self.__class__.__name__)

    class TestDataset(Dataset):
        Params = type("P", (ParamsManagerAbstract,), {"__init__": init})
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
        Params = type("P", (ParamsManagerAbstract,), {"setup": setup})
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
