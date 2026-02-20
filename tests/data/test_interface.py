"""Test main interface and modules features."""

import pytest

from neba.data import (
    DataInterface,
    LoaderAbstract,
    ParametersAbstract,
    ParametersDict,
    SourceAbstract,
    WriterAbstract,
)
from neba.data.module import ModuleMix


def test_abstract_interface():
    """Simple sanity test."""

    class MyDataInterface(DataInterface):
        pass

    assert issubclass(MyDataInterface.Parameters, ParametersAbstract)
    assert issubclass(MyDataInterface.Source, SourceAbstract)
    assert issubclass(MyDataInterface.Loader, LoaderAbstract)
    assert issubclass(MyDataInterface.Writer, WriterAbstract)

    di = MyDataInterface()
    assert isinstance(di.parameters, ParametersAbstract)
    assert isinstance(di.source, SourceAbstract)
    assert isinstance(di.loader, LoaderAbstract)
    assert isinstance(di.writer, WriterAbstract)


def test_interface_custom():
    """Test module definition."""

    # external module definition
    class P(ParametersAbstract):
        pass

    class S(SourceAbstract):
        pass

    class MyDataInterface(DataInterface):
        Parameters = P
        Source = S

        # internal definition
        class Loader(LoaderAbstract):
            pass

        class Writer(WriterAbstract):
            pass

    di = MyDataInterface()
    assert isinstance(di.parameters, P)
    assert isinstance(di.source, S)
    assert isinstance(di.loader, MyDataInterface.Loader)
    assert isinstance(di.writer, MyDataInterface.Writer)


def test_instantiate_order():
    """Check the instantiation order of modules is the one frome _modules_attributes."""
    order = []

    def init(self, *args, **kwargs):
        order.append(self.__class__.__name__)

    class MyDataInterface(DataInterface):
        Parameters = type("P", (ParametersAbstract,), {"__init__": init})
        Source = type("S", (SourceAbstract,), {"__init__": init})
        Loader = type("L", (LoaderAbstract,), {"__init__": init})
        Writer = type("W", (WriterAbstract,), {"__init__": init})

    MyDataInterface()
    assert order == ["P", "S", "L", "W"]


def test_parent_interface_access():
    """Test backref to parent interface."""

    class MyDataInterface(DataInterface):
        pass

    di = MyDataInterface()
    for mod in di._modules.values():
        assert mod.di is di


def test_module_setup():
    """Test all modules are setup, and in order."""
    order = []

    def setup(self, *args, **kwargs):
        order.append(self.__class__.__name__)

    class MyDataInterface(DataInterface):
        Parameters = type("P", (ParametersAbstract,), {"setup": setup})
        Source = type("S", (SourceAbstract,), {"setup": setup})
        Loader = type("L", (LoaderAbstract,), {"setup": setup})
        Writer = type("W", (WriterAbstract,), {"setup": setup})

    di = MyDataInterface()
    assert order == ["P", "S", "L", "W"]
    for mod in di._modules.values():
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

    class MyDataInterface(DataInterface):
        class Source(SourceA, SourceB):
            def setup(self):
                super().setup()

    MyDataInterface()
    assert is_setup == {"A", "B", "C"}


def test_str():
    class OnlyID(DataInterface):
        ID = "MyID"

    class OnlyShortname(DataInterface):
        SHORTNAME = "MySHORTNAME"

    class Both(DataInterface):
        ID = "MyID"
        SHORTNAME = "MySHORTNAME"

    class Neither(DataInterface):
        pass

    assert str(OnlyID()) == "MyID (OnlyID)"
    assert str(OnlyShortname()) == "MySHORTNAME (OnlyShortname)"
    assert str(Both()) == "MySHORTNAME:MyID (Both)"
    assert str(Neither()) == "Neither"


def test_reset_callbacks():
    class MyDataInterface(DataInterface):
        called = False
        called_bis = False

    def callback(di, **kwargs):
        di.called = True

    def callback_bis(di, **kwargs):
        di.called_bis = True

    di = MyDataInterface()
    di.register_callback("test_callback", callback)
    di.register_callback("test_callback_bis", callback_bis)

    with pytest.raises(KeyError):
        di.register_callback("test_callback", callback)

    assert not di.called
    assert not di.called_bis
    di.trigger_callbacks()
    assert di.called
    assert di.called_bis

    di.called = False
    di.called_bis = False

    di.trigger_callbacks(False)
    assert not di.called
    assert not di.called_bis

    di.trigger_callbacks(["test_callback_bis"])
    assert not di.called
    assert di.called_bis


def test_get_data_sets():
    class MyDataInterface(DataInterface):
        Parameters = ParametersDict

        # just return a copy of parameters as data
        def get_data(self, **kwargs):
            return dict(self.parameters.direct)

    di = MyDataInterface(a=0, b=0)

    params_maps = [
        {"a": 0, "b": 0, "c": 0},
        {"a": 1, "b": 0, "c": 1},
        {"a": 2, "b": 3, "c": 4},
    ]
    data = di.get_data_sets(params_maps)
    assert data == params_maps
    assert di.parameters.direct == dict(a=0, b=0)

    data = di.get_data_sets(
        params_sets=[
            ["a", "b", "c"],
            [0, 0, 0],
            [1, 0, 1],
            [2, 3, 4],
        ]
    )
    assert data == params_maps
    assert di.parameters.direct == dict(a=0, b=0)


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

        class MyDataInterface(DataInterface):
            Source = ModuleMix.create([SourceA, SourceB])

        MyDataInterface()
        assert is_setup == {"A", "B", "C"}
