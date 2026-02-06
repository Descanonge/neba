"""Test Dataset parameters modules."""

from traitlets import Float, Int, Unicode

from neba.config import ApplicationBase, Section
from neba.data import (
    Dataset,
    ParamsManagerApp,
    ParamsManagerDict,
    ParamsManagerSection,
)


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
        dm._register_callback("test_callback", self.callback)

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

    def test_section(self):
        class Config(Section):
            a = Int(0)

        class DatasetSection(Dataset):
            ParamsManager = ParamsManagerSection.new(Config)
            called = False

        dm = DatasetSection()
        dm._register_callback("test_callback", self.callback)

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

    def test_app(self):
        class App(ApplicationBase):
            a = Int(0)

        class DatasetApp(Dataset):
            ParamsManager = ParamsManagerApp
            called = False

        app = App(start=False)
        dm = DatasetApp(app)
        dm._register_callback("test_calback", self.callback)

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
        class App(ApplicationBase):
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


def test_params_excursion():
    class TestDataset(Dataset):
        ParamsManager = ParamsManagerDict

    dm = TestDataset(dict(a=0, b=1))

    with dm.save_excursion():
        dm.set_params(a=5)
        assert dm.params["a"] == 5
        assert dm.params["b"] == 1

    assert dm.params["a"] == 0
    assert dm.params["b"] == 1

    with dm.save_excursion():
        dm.reset_params(a=5)
        assert dm.params == dict(a=5)

    assert dm.params["a"] == 0
    assert dm.params["b"] == 1
