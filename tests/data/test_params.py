"""Test Dataset parameters modules."""

import pytest
from traitlets import Float, Int, Unicode

from neba.config import Application, Section
from neba.data import (
    CachedModule,
    Dataset,
    DatasetSection,
    LoaderAbstract,
    ParametersApp,
    ParametersDict,
    ParametersSection,
    autocached,
)


class TestPassingParams:
    """Passing the parameters when creating the dataset."""

    def test_dict(self):
        class MyDataset(Dataset):
            Parameters = ParametersDict

        dm = MyDataset({"a": 0, "b": "test"}, a=1, c=0.0)
        assert dm.parameters.direct == {"a": 1, "b": "test", "c": 0.0}

    def test_section(self):
        class Config(Section):
            a = Int(0)
            b = Unicode("test")

            class sub(Section):
                c = Float(0.0)

        class MyDataset(Dataset):
            Parameters = ParametersSection.new(Config)

        # only default values
        dm = MyDataset()
        assert dm.parameters.direct == Config()

        config = Config(a=1, b="other", **{"sub.c": 2.0})
        dm = MyDataset(config)
        assert dm.parameters.direct == config
        assert dm.parameters.direct.a == 1
        assert dm.parameters.direct.b == "other"
        assert dm.parameters.direct.sub.c == 2.0

        dm = MyDataset(config, a=2)
        assert dm.parameters.direct.a == 2

    def test_app(self):
        class App(Application):
            a = Int(0)
            b = Unicode("test")
            c = Float(0.0)

        class DatasetApp(Dataset):
            Parameters = ParametersApp

        app = App(start=False)
        app.a = 1
        dm = DatasetApp(app)
        assert dm.parameters.direct == app
        assert dm.parameters.direct.a == 1
        assert dm.parameters.direct.b == "test"
        assert dm.parameters.direct.c == 0.0

        dm = DatasetApp(app, a=2)
        assert dm.parameters.direct.a == 2

    def test_dataset_section(self):
        class MySection(Section):
            a = Int(0)
            c = Int(0)

        class MyDataset(DatasetSection):
            Parameters = ParametersSection.new(MySection)
            a = Int(1)
            b = Int(0)

        section = MySection()
        dm = MyDataset(section, b=2, c=2)
        assert dm.b == 2
        assert dm.parameters.direct.c == 2

        with pytest.raises(KeyError):
            MyDataset(section, a=1)


class TestSettingParameters:
    """Test modifiying parameters using the module API."""

    def test_dict(self):
        class MyDataset(Dataset):
            Parameters = ParametersDict

        dm = MyDataset({"a": 0}, b=1)
        assert dm.parameters.get("a") == 0
        assert dm.parameters["a"] == 0
        assert dm.parameters.get("b") == 1
        assert dm.parameters["b"] == 1

        assert dm.parameters.get("wrong", None) is None
        with pytest.raises(KeyError):
            dm.parameters["wrong"]

        dm.parameters.set("c", 2)
        assert dm.parameters.get("c") == 2
        dm.parameters["c"] = 3
        assert dm.parameters.get("c") == 3

        dm.parameters.update({"a": 10, "b": 11, "d": 14})
        assert dm.parameters.direct == dict(a=10, b=11, c=3, d=14)

    def test_section(self):
        class Config(Section):
            a = Int(0)
            b = Int(1)

            class sub(Section):
                c = Float(0.0)

        class MyDataset(Dataset):
            Parameters = ParametersSection.new(Config)

        dm = MyDataset({"a": 0, "sub.c": 2.0}, b=1)
        assert dm.parameters.get("a") == 0
        assert dm.parameters["a"] == 0
        assert dm.parameters.get("b") == 1
        assert dm.parameters["b"] == 1
        assert dm.parameters.get("sub.c") == 2.0
        assert dm.parameters["sub.c"] == 2.0

        assert dm.parameters.get("wrong", None) is None
        with pytest.raises(KeyError):
            dm.parameters["wrong"]
        with pytest.raises(KeyError):
            dm.parameters["sub.wrong"]

        dm.parameters.set("sub.c", 3.0)
        assert dm.parameters.get("sub.c") == 3.0
        dm.parameters["sub.c"] = 4.0
        assert dm.parameters.get("sub.c") == 4.0

        dm.parameters.update({"a": 10, "b": 11, "sub.c": 12})
        assert dm.parameters.direct.a == 10
        assert dm.parameters.direct.b == 11
        assert dm.parameters.direct.sub.c == 12.0

        # New traits
        with pytest.raises(KeyError):
            dm.parameters["new_trait"] = 0

        dm.parameters.allow_new = True
        dm.parameters["new_trait_1"] = Int(5)
        assert dm.parameters.direct.new_trait_1 == 5
        dm.parameters.update(new_trait_2=Int(6))
        assert dm.parameters.direct.new_trait_2 == 6


class CallbackTest:
    """Context for testing if callback is called inside it."""

    def __init__(self, dm: Dataset, is_called: bool = True):
        self.dm = dm
        self.is_called = is_called

    def __enter__(self):
        self.dm.called = False

    def __exit__(self, *exc):
        assert self.dm.called is self.is_called
        return False


class TestCacheCallback:
    """Test that modifying a parameter triggers callback."""

    @staticmethod
    def callback(dm, **kwargs):
        dm.called = True

    def test_dict(self):
        class MyDataset(Dataset):
            Parameters = ParametersDict
            called = False

        dm = MyDataset()
        dm.register_callback("test_callback", self.callback)

        # module API
        with CallbackTest(dm):
            dm.parameters.reset()

        with CallbackTest(dm):
            dm.parameters.update({"a": 0})

        with CallbackTest(dm):
            # even if no change
            dm.parameters["a"] = 0

        # Changing directly
        # new parameter:
        with CallbackTest(dm):
            dm.parameters.direct["b"] = 0

        # change that parameter
        with CallbackTest(dm):
            dm.parameters.direct["b"] = 1

        # if identical, no callback
        with CallbackTest(dm, is_called=False):
            dm.parameters.direct["b"] = 1

    def test_section(self) -> None:
        class MySection(Section):
            a = Int(0)

            class sub(Section):
                b = Int(0)

        class MyDataset(Dataset):
            Parameters = ParametersSection.new(MySection)
            Parameters.allow_new = True
            called = False

        dm = MyDataset()
        dm.register_callback("test_callback", self.callback)

        # module API
        with CallbackTest(dm):
            dm.parameters.reset()

        with CallbackTest(dm):
            dm.parameters.update({"a": 0})

        with CallbackTest(dm):
            # even if no change
            dm.parameters["a"] = 0

        # Changing directly
        # with setattr
        with CallbackTest(dm):
            dm.parameters.direct.a = 1
        with CallbackTest(dm):
            dm.parameters.direct.sub.b = 1

        # with setitem
        with CallbackTest(dm):
            dm.parameters.direct["a"] = 2
        with CallbackTest(dm):
            dm.parameters.direct["sub.b"] = 2

        # if identical, no callback
        with CallbackTest(dm, is_called=False):
            dm.parameters.direct["a"] = 2
        with CallbackTest(dm, is_called=False):
            dm.parameters.direct["sub.b"] = 2

        # reset
        with CallbackTest(dm):
            dm.parameters.direct.reset()

        # new trait
        with CallbackTest(dm):
            dm.parameters.update(b=Int(1))
        assert dm.parameters.direct.b == 1
        with CallbackTest(dm):
            dm.parameters.direct.b = 2

    def test_dataset_section(self):
        class MyDataset(DatasetSection):
            Parameters = ParametersDict
            called = False

            a = Int(0)

            class sub(Section):
                b = Int(0)

        dm = MyDataset(b=0)
        dm.register_callback("test_callback", self.callback)

        with CallbackTest(dm):
            dm.a = 1
        with CallbackTest(dm):
            dm.sub.b = 1

        # no change
        with CallbackTest(dm, is_called=False):
            dm.a = 1
        with CallbackTest(dm, is_called=False):
            dm.sub.b = 1


def test_autocached():
    class MyDataset(Dataset):
        Parameters = ParametersDict

        class Loader(LoaderAbstract, CachedModule):
            @property
            @autocached
            def test_property(self):
                return 0

            @autocached
            def test_method(self):
                return 1

    dm = MyDataset()
    assert len(dm.loader.cache) == 0

    _ = dm.loader.test_property
    assert dm.loader.cache == dict(test_property=0)

    _ = dm.loader.test_method()
    assert dm.loader.cache == dict(test_property=0, test_method=1)

    dm.trigger_callbacks()
    assert len(dm.loader.cache) == 0


class TestParamsExcursion:
    def test_dict(self):
        class MyDataset(Dataset):
            Parameters = ParametersDict

        dm = MyDataset(dict(a=0, b=1))

        with dm.save_excursion():
            dm.parameters["a"] = 5
            assert dm.parameters.direct == dict(a=5, b=1)

        assert dm.parameters.direct == dict(a=0, b=1)

        with dm.save_excursion():
            dm.parameters.reset()
            dm.parameters.update(a=5, c=1)
            assert dm.parameters.direct == dict(a=5, c=1)

        assert dm.parameters.direct == dict(a=0, b=1)

    def test_dict_cache(self):
        class MyDataset(Dataset):
            Parameters = ParametersDict

            class Loader(LoaderAbstract, CachedModule):
                pass

        dm = MyDataset(dict(a=0, b=1))
        dm.loader.cache["test"] = 0
        with dm.save_excursion(save_cache=True):
            dm.parameters["a"] = 5
            dm.loader.cache["test"] = 1

        assert dm.parameters.direct == dict(a=0, b=1)
        assert dm.loader.cache["test"] == 0

    def test_section(self):
        class MySection(Section):
            a = Int(0)
            b = Int(1)

        class MyDataset(Dataset):
            Parameters = ParametersSection.new(MySection)

        dm = MyDataset()

        with dm.save_excursion():
            dm.parameters["a"] = 5
            assert dm.parameters["a"] == 5
            assert dm.parameters["b"] == 1

        assert dm.parameters["a"] == 0
        assert dm.parameters["b"] == 1

        with dm.save_excursion():
            dm.parameters["a"] = 5
            assert dm.parameters["a"] == 5
            assert dm.parameters["b"] == 1

        assert dm.parameters["a"] == 0
        assert dm.parameters["b"] == 1

    def test_section_cache(self):
        class MySection(Section):
            a = Int(0)
            b = Int(1)

        class MyDataset(Dataset):
            Parameters = ParametersSection.new(MySection)

            class Loader(LoaderAbstract, CachedModule):
                pass

        dm = MyDataset()
        dm.loader.cache["test"] = 0
        with dm.save_excursion(save_cache=True):
            dm.parameters["a"] = 5
            dm.loader.cache["test"] = 1

        assert dm.parameters["a"] == 0
        assert dm.parameters["b"] == 1
        assert dm.loader.cache["test"] == 0
