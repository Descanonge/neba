"""Test Dataset parameters modules."""

import pytest
from traitlets import Float, Int, Unicode

from neba.config import Application, Section
from neba.data import (
    CachedModule,
    Dataset,
    DatasetSection,
    LoaderAbstract,
    ParamsManagerApp,
    ParamsManagerDict,
    ParamsManagerSection,
    autocached,
)


class TestPassingParams:
    """Passing the parameters when creating the dataset."""

    def test_dict(self):
        class DatasetDict(Dataset):
            ParamsManager = ParamsManagerDict

        dm = DatasetDict({"a": 0, "b": "test"}, a=1, c=0.0)
        assert dm.params == {"a": 1, "b": "test", "c": 0.0}

    def test_section(self):
        class Config(Section):
            a = Int(0)
            b = Unicode("test")
            c = Float(0.0)

        class DatasetSection(Dataset):
            ParamsManager = ParamsManagerSection.new(Config)

        # only default values
        dm = DatasetSection()
        assert dm.params == Config()

        config = Config(a=1, b="other")
        dm = DatasetSection(config)
        assert dm.params == config
        assert dm.params.a == 1
        assert dm.params.b == "other"
        assert dm.params.c == 0.0

        dm = DatasetSection(config, a=2)
        assert dm.params.a == 2

    def test_app(self):
        class App(Application):
            a = Int(0)
            b = Unicode("test")
            c = Float(0.0)

        class DatasetApp(Dataset):
            ParamsManager = ParamsManagerApp

        app = App(start=False)
        app.a = 1
        dm = DatasetApp(app)
        assert dm.params == app
        assert dm.params.a == 1
        assert dm.params.b == "test"
        assert dm.params.c == 0.0

        dm = DatasetApp(app, a=2)
        assert dm.params.a == 2

    def test_dataset_section(self):
        class MySection(Section):
            a = Int(0)
            c = Int(0)

        class MyDataset(DatasetSection):
            ParamsManager = ParamsManagerSection.new(MySection)
            a = Int(1)
            b = Int(0)

        section = MySection()
        dm = MyDataset(section, b=2, c=2)
        assert dm.b == 2
        assert dm.params.c == 2

        with pytest.raises(KeyError):
            MyDataset(section, a=1)


class TestCacheCallback:
    """Test that modifying a parameter triggers callback."""

    @staticmethod
    def callback(dm, **kwargs):
        dm.called = True

    def test_dict(self):
        class DatasetDict(Dataset):
            ParamsManager = ParamsManagerDict
            called = False

        dm = DatasetDict()
        dm.register_callback("test_callback", self.callback)

        # reset_params
        dm.called = False
        dm.reset_params()
        assert dm.called

        # update_params
        dm.called = False
        dm.update_params()
        assert dm.called

        # set a parameter
        dm.called = False
        dm.params["a"] = 0
        assert dm.called

        # change that parameter
        dm.called = False
        dm.params["a"] = 1
        assert dm.called

        # if identical, no callback
        dm.called = False
        dm.params["a"] = 1
        assert not dm.called

    def test_section(self) -> None:
        class Config(Section):
            a = Int(0)

        class DatasetSection(Dataset):
            ParamsManager = ParamsManagerSection.new(Config)
            ParamsManager.RAISE_ON_MISS = False
            called = False

        dm = DatasetSection()
        dm.register_callback("test_callback", self.callback)

        # reset_params
        dm.called = False
        dm.reset_params()
        assert dm.called

        # update_params
        dm.called = False
        dm.update_params()
        assert dm.called

        # with setitem
        dm.called = False
        dm.params["a"] = 1
        assert dm.called

        # with setattr
        dm.called = False
        dm.params.a = 2
        assert dm.called

        # if identical, no callback
        dm.called = False
        dm.params["a"] = 2
        assert not dm.called

        # reset and setattr
        dm.params.reset()
        dm.called = False
        dm.params.a = 1
        assert dm.called

        # new trait
        dm.update_params(b=Int(1))
        dm.called = True
        assert dm.params.b == 1
        dm.called = False
        dm.params.b = 2
        assert dm.called

    def test_app(self):
        class App(Application):
            a = Int(0)

        class DatasetApp(Dataset):
            ParamsManager = ParamsManagerApp
            called = False

        app = App(start=False)
        dm = DatasetApp(app)
        dm.register_callback("test_callback", self.callback)

        # reset_params
        dm.called = False
        dm.reset_params()
        assert dm.called

        # update_params
        dm.called = False
        dm.update_params()
        assert dm.called

        # with setitem
        dm.called = False
        dm.params["a"] = 1
        assert dm.called

        # with setattr
        dm.called = False
        dm.params.a = 2
        assert dm.called

        # if identical, no callback
        dm.called = False
        dm.params["a"] = 2
        assert not dm.called


def test_autocached():
    class MyDataset(Dataset):
        ParamsManager = ParamsManagerDict

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
        class TestDataset(Dataset):
            ParamsManager = ParamsManagerDict

        dm = TestDataset(dict(a=0, b=1))

        with dm.save_excursion():
            dm.update_params(a=5)
            assert dm.params["a"] == 5
            assert dm.params["b"] == 1

        assert dm.params == dict(a=0, b=1)

        with dm.save_excursion():
            dm.reset_params()
            dm.update_params(a=5, c=1)
            assert dm.params == dict(a=5, c=1)

        assert dm.params == dict(a=0, b=1)

    def test_dict_cache(self):
        class TestDataset(Dataset):
            ParamsManager = ParamsManagerDict

            class Loader(LoaderAbstract, CachedModule):
                pass

        dm = TestDataset(dict(a=0, b=1))
        dm.loader.cache["test"] = 0
        with dm.save_excursion(save_cache=True):
            dm.update_params(a=5)
            dm.loader.cache["test"] = 1

        assert dm.params == dict(a=0, b=1)
        assert dm.loader.cache["test"] == 0

    def test_section(self):
        class MyParams(Section):
            a = Int(0)
            b = Int(1)

        class TestDataset(Dataset):
            ParamsManager = ParamsManagerSection.new(MyParams)

        dm = TestDataset()

        with dm.save_excursion():
            dm.update_params(a=5)
            assert dm.params.a == 5
            assert dm.params.b == 1

        assert dm.params.a == 0
        assert dm.params.b == 1

        with dm.save_excursion():
            dm.update_params(a=5)
            assert dm.params.a == 5
            assert dm.params.b == 1

        assert dm.params.a == 0
        assert dm.params.b == 1

    def test_section_cache(self):
        class MyParams(Section):
            a = Int(0)
            b = Int(1)

        class TestDataset(Dataset):
            ParamsManager = ParamsManagerSection.new(MyParams)

            class Loader(LoaderAbstract, CachedModule):
                pass

        dm = TestDataset()
        dm.loader.cache["test"] = 0
        with dm.save_excursion(save_cache=True):
            dm.update_params(a=5)
            dm.loader.cache["test"] = 1

        assert dm.params.a == 0
        assert dm.params.b == 1
        assert dm.loader.cache["test"] == 0
