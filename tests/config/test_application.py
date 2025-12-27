"""Test more integrated features of the Application."""

import pytest
from traitlets import Float, Int

from data_assistant.config.application import ApplicationBase
from data_assistant.config.loaders import ConfigValue, FileLoader
from data_assistant.config.loaders.json import JsonLoader
from data_assistant.config.loaders.python import PyLoader
from data_assistant.config.loaders.toml import TomlkitLoader
from data_assistant.config.loaders.yaml import YamlLoader
from tests.config.generic_config import GenericConfig, GenericConfigInfo
from tests.conftest import todo


class App(ApplicationBase, GenericConfig):
    pass


@todo
def test_logger():
    # test it goes to the correct logger ? idk
    assert 0


class TestStartup:
    def test_ignore_cli(self):
        # value different than what is defined in config.py and config.toml
        app = App(argv=["--int", "2"], ignore_cli=True)
        assert len(app.cli_conf) == 0
        assert app.int != 2

    def test_no_start(self):
        new_val = GenericConfigInfo.default("int") + 1
        app = App(argv=["--int", str(new_val)], start=False)
        assert len(app.conf) == 0
        assert len(app.cli_conf) == 0
        assert len(app.file_conf) == 0
        assert app.int == GenericConfigInfo.default("int")
        assert app.str == GenericConfigInfo.default("str")


class TestCLIParsing:
    def test_add_extra_parameter(self):
        class AppExtra(App):
            pass

        AppExtra.add_extra_parameters(int=Int(0))
        AppExtra.add_extra_parameters(float=Float(0.0))

        app = AppExtra(argv=["--int=0", "--extra.int=1", "--extra.float=1"])
        assert app.int == 0
        assert app.extra.int == 1
        assert app.extra.float == 1.0


@pytest.mark.parametrize(
    ["filename", "loader"],
    [
        ("config.py", PyLoader),
        ("config.toml", TomlkitLoader),
        ("config.json", JsonLoader),
        ("config.yaml", YamlLoader),
    ],
)
def test_select_file_loader(filename: str, loader: type[FileLoader]):
    app = App(start=False)
    assert issubclass(app._select_file_loader(filename), loader)


def test_resolve_config():
    app = App(start=False)
    app._init_subsections({})

    # normal keys
    cv = ConfigValue(2, "int")
    out = app.resolve_config_value(cv)
    assert out.input == 2
    assert out.key == "int"
    assert out.trait is app.traits()["int"]
    assert isinstance(app, out.container_cls)

    cv = ConfigValue(3, "deep_sub.sub_generic_deep.int")
    out = app.resolve_config_value(cv)
    assert out.input == 3
    assert out.key == "deep_sub.sub_generic_deep.int"
    assert out.trait is app.deep_sub.sub_generic_deep.traits()["int"]
    assert isinstance(app.deep_sub.sub_generic_deep, out.container_cls)

    # aliases
    cv = ConfigValue(4, "deep_short.int")
    out = app.resolve_config_value(cv)
    assert out.input == 4
    assert out.key == "deep_sub.sub_generic_deep.int"
    assert out.trait is app.deep_sub.sub_generic_deep.traits()["int"]
    assert isinstance(app.deep_sub.sub_generic_deep, out.container_cls)
