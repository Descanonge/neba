"""Test parameters modules."""

import pytest
from traitlets import Float, Int, Unicode

from neba.config import Application, Section
from neba.data import (
    CachedModule,
    DataInterface,
    DataInterfaceSection,
    LoaderAbstract,
    ParametersApp,
    ParametersDict,
    ParametersSection,
    autocached,
)


class TestPassingParams:
    """Passing the parameters when creating the interface."""

    def test_dict(self):
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

        di = MyDataInterface({"a": 0, "b": "test"}, a=1, c=0.0)
        assert di.parameters.direct == {"a": 1, "b": "test", "c": 0.0}

    def test_section(self):
        class Config(Section):
            a = Int(0)
            b = Unicode("test")

            class sub(Section):
                c = Float(0.0)

        class MyDataInterface(DataInterface):
            Parameters = ParametersSection.new(Config)

        # only default values
        di = MyDataInterface()
        assert di.parameters.direct == Config()

        config = Config(a=1, b="other", **{"sub.c": 2.0})
        di = MyDataInterface(config)
        assert di.parameters.direct == config
        assert di.parameters.direct.a == 1
        assert di.parameters.direct.b == "other"
        assert di.parameters.direct.sub.c == 2.0

        di = MyDataInterface(config, a=2)
        assert di.parameters.direct.a == 2

    def test_app(self):
        class MyApp(Application):
            a = Int(0)
            b = Unicode("test")
            c = Float(0.0)

        class MyDataInterface(DataInterface):
            Parameters = ParametersApp

        app = MyApp(start=False)
        app.a = 1
        di = MyDataInterface(app)
        assert di.parameters.direct == app
        assert di.parameters.direct.a == 1
        assert di.parameters.direct.b == "test"
        assert di.parameters.direct.c == 0.0

        di = MyDataInterface(app, a=2)
        assert di.parameters.direct.a == 2

    def test_interface_section(self):
        class MySection(Section):
            a = Int(0)
            c = Int(0)

        class MyDataInterface(DataInterfaceSection):
            Parameters = ParametersSection.new(MySection)
            a = Int(1)
            b = Int(0)

        section = MySection()
        di = MyDataInterface(section, b=2, c=2)
        assert di.b == 2
        assert di.parameters.direct.c == 2

        with pytest.raises(KeyError):
            MyDataInterface(section, a=1)


class TestSettingParameters:
    """Test modifiying parameters using the module API."""

    def test_dict(self):
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

        di = MyDataInterface({"a": 0}, b=1)
        assert di.parameters.get("a") == 0
        assert di.parameters["a"] == 0
        assert di.parameters.get("b") == 1
        assert di.parameters["b"] == 1

        assert di.parameters.get("wrong", None) is None
        with pytest.raises(KeyError):
            di.parameters["wrong"]

        di.parameters.set("c", 2)
        assert di.parameters.get("c") == 2
        di.parameters["c"] = 3
        assert di.parameters.get("c") == 3

        di.parameters.update({"a": 10, "b": 11, "d": 14})
        assert di.parameters.direct == dict(a=10, b=11, c=3, d=14)

    def test_section(self):
        class Config(Section):
            a = Int(0)
            b = Int(1)

            class sub(Section):
                c = Float(0.0)

        class MyDataInterface(DataInterface):
            Parameters = ParametersSection.new(Config)

        di = MyDataInterface({"a": 0, "sub.c": 2.0}, b=1)
        assert di.parameters.get("a") == 0
        assert di.parameters["a"] == 0
        assert di.parameters.get("b") == 1
        assert di.parameters["b"] == 1
        assert di.parameters.get("sub.c") == 2.0
        assert di.parameters["sub.c"] == 2.0

        assert di.parameters.get("wrong", None) is None
        with pytest.raises(KeyError):
            di.parameters["wrong"]
        with pytest.raises(KeyError):
            di.parameters["sub.wrong"]

        di.parameters.set("sub.c", 3.0)
        assert di.parameters.get("sub.c") == 3.0
        di.parameters["sub.c"] = 4.0
        assert di.parameters.get("sub.c") == 4.0

        di.parameters.update({"a": 10, "b": 11, "sub.c": 12})
        assert di.parameters.direct.a == 10
        assert di.parameters.direct.b == 11
        assert di.parameters.direct.sub.c == 12.0

        # New traits
        with pytest.raises(KeyError):
            di.parameters["new_trait"] = 0

        di.parameters.allow_new = True
        di.parameters["new_trait_1"] = Int(5)
        assert di.parameters.direct.new_trait_1 == 5
        di.parameters.update(new_trait_2=Int(6))
        assert di.parameters.direct.new_trait_2 == 6


class CallbackTest:
    """Context for testing if callback is called inside it."""

    def __init__(self, di: DataInterface, is_called: bool = True):
        self.di = di
        self.is_called = is_called

    def __enter__(self):
        self.di.called = False

    def __exit__(self, *exc):
        assert self.di.called is self.is_called
        return False


class TestCacheCallback:
    """Test that modifying a parameter triggers callback."""

    @staticmethod
    def callback(di, **kwargs):
        di.called = True

    def test_dict(self):
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict
            called = False

        di = MyDataInterface()
        di.register_callback("test_callback", self.callback)

        # module API
        with CallbackTest(di):
            di.parameters.reset()

        with CallbackTest(di):
            di.parameters.update({"a": 0})

        with CallbackTest(di):
            # even if no change
            di.parameters["a"] = 0

        # Changing directly
        # new parameter:
        with CallbackTest(di):
            di.parameters.direct["b"] = 0

        # change that parameter
        with CallbackTest(di):
            di.parameters.direct["b"] = 1

        # if identical, no callback
        with CallbackTest(di, is_called=False):
            di.parameters.direct["b"] = 1

        # using update
        with CallbackTest(di):
            di.parameters.update(b=2)

    def test_section(self) -> None:
        class MySection(Section):
            a = Int(0)

            class sub(Section):
                b = Int(0)

        class MyDataInterface(DataInterface):
            Parameters = ParametersSection.new(MySection)
            Parameters.allow_new = True
            called = False

        di = MyDataInterface()
        di.register_callback("test_callback", self.callback)

        # module API
        with CallbackTest(di):
            di.parameters.reset()

        with CallbackTest(di):
            di.parameters.update({"a": 0})

        with CallbackTest(di):
            # even if no change
            di.parameters["a"] = 0

        # Changing directly
        # with setattr
        with CallbackTest(di):
            di.parameters.direct.a = 1
        with CallbackTest(di):
            di.parameters.direct.sub.b = 1

        # with setitem
        with CallbackTest(di):
            di.parameters.direct["a"] = 2
        with CallbackTest(di):
            di.parameters.direct["sub.b"] = 2

        # if identical, no callback
        with CallbackTest(di, is_called=False):
            di.parameters.direct["a"] = 2
        with CallbackTest(di, is_called=False):
            di.parameters.direct["sub.b"] = 2

        # reset
        with CallbackTest(di):
            di.parameters.direct.reset()

        # new trait
        with CallbackTest(di):
            di.parameters.update(b=Int(1))
        assert di.parameters.direct.b == 1
        with CallbackTest(di):
            di.parameters.direct.b = 2

    def test_interface_section(self):
        class MyDataInterface(DataInterfaceSection):
            Parameters = ParametersDict
            called = False

            a = Int(0)

            class sub(Section):
                b = Int(0)

        di = MyDataInterface(b=0)
        di.register_callback("test_callback", self.callback)

        with CallbackTest(di):
            di.a = 1
        with CallbackTest(di):
            di.sub.b = 1

        # no change
        with CallbackTest(di, is_called=False):
            di.a = 1
        with CallbackTest(di, is_called=False):
            di.sub.b = 1


class TestCachedModule:

    def get_interface(self):
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

            class Loader(LoaderAbstract, CachedModule):
                @property
                @autocached
                def test_property(self):
                    return 0

                @autocached
                def test_method(self):
                    return 1

        return MyDataInterface

    def test_autocached(self):
        di = self.get_interface()()
        assert len(di.loader.cache) == 0

        _ = di.loader.test_property
        assert di.loader.cache == dict(test_property=0)

        _ = di.loader.test_method()
        assert di.loader.cache == dict(test_property=0, test_method=1)

        di.trigger_callbacks()
        assert len(di.loader.cache) == 0

    def test_disable(self):
        di_cls = self.get_interface()
        di_cls.Loader._add_void_callback = False
        di = di_cls()

        assert len(di._reset_callbacks) == 0

        _ = di.loader.test_property
        assert "test_property" in di.loader.cache
        di.trigger_callbacks()
        assert "test_property" in di.loader.cache



class TestParamsExcursion:
    def test_dict(self):
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

        di = MyDataInterface(dict(a=0, b=1))

        with di.save_excursion():
            di.parameters["a"] = 5
            assert di.parameters.direct == dict(a=5, b=1)

        assert di.parameters.direct == dict(a=0, b=1)

        with di.save_excursion():
            di.parameters.reset()
            di.parameters.update(a=5, c=1)
            assert di.parameters.direct == dict(a=5, c=1)

        assert di.parameters.direct == dict(a=0, b=1)

    def test_dict_cache(self):
        class MyDataInterface(DataInterface):
            Parameters = ParametersDict

            class Loader(LoaderAbstract, CachedModule):
                pass

        di = MyDataInterface(dict(a=0, b=1))
        di.loader.cache["test"] = 0
        with di.save_excursion(save_cache=True):
            di.parameters["a"] = 5
            di.loader.cache["test"] = 1

        assert di.parameters.direct == dict(a=0, b=1)
        assert di.loader.cache["test"] == 0

    def test_section(self):
        class MySection(Section):
            a = Int(0)
            b = Int(1)

        class MyDataInterface(DataInterface):
            Parameters = ParametersSection.new(MySection)

        di = MyDataInterface()

        with di.save_excursion():
            di.parameters["a"] = 5
            assert di.parameters["a"] == 5
            assert di.parameters["b"] == 1

        assert di.parameters["a"] == 0
        assert di.parameters["b"] == 1

        with di.save_excursion():
            di.parameters["a"] = 5
            assert di.parameters["a"] == 5
            assert di.parameters["b"] == 1

        assert di.parameters["a"] == 0
        assert di.parameters["b"] == 1

    def test_section_cache(self):
        class MySection(Section):
            a = Int(0)
            b = Int(1)

        class MyDataInterface(DataInterface):
            Parameters = ParametersSection.new(MySection)

            class Loader(LoaderAbstract, CachedModule):
                pass

        di = MyDataInterface()
        di.loader.cache["test"] = 0
        with di.save_excursion(save_cache=True):
            di.parameters["a"] = 5
            di.loader.cache["test"] = 1

        assert di.parameters["a"] == 0
        assert di.parameters["b"] == 1
        assert di.loader.cache["test"] == 0
