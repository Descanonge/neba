"""Test more integrated features of the Application."""

import logging

import pytest
from traitlets import Float, Int

from neba.config.application import ApplicationBase
from neba.config.loaders import ConfigValue, FileLoader
from neba.config.loaders.json import JsonLoader
from neba.config.loaders.python import PyLoader
from neba.config.loaders.toml import TomlkitLoader
from neba.config.loaders.yaml import YamlLoader
from neba.config.util import ConfigError
from tests.config.generic_config import GenericConfig, GenericConfigInfo


class App(ApplicationBase, GenericConfig):
    pass


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
    app._init_subsections({})  # make it easier to access subsections in test

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

    # unknown key error
    cv = ConfigValue(0, "int_", origin="test")
    with pytest.raises(ConfigError) as excinfo:
        out = app.resolve_config_value(cv)
    notes = excinfo.value.__notes__
    assert notes == [
        "Did you mean 'int'?",
        "Error in configuration key 'int_' from test.",
    ]


class TestLogger:
    def test_config(self, capsys):
        app = App(ignore_cli=True)
        fmt = "For test:: %(message)s"
        app.log_format = fmt
        app.log_level = "WARN"

        logger = logging.getLogger("tests.config.test_application.App")
        assert app.log is logger
        assert logger.level == logging.WARN

        formatter = logger.handlers[0].formatter
        assert formatter._fmt == fmt

    def test_level(self, capsys):
        app = App(ignore_cli=True)

        app.log_level = 42
        assert app.log.level == 42

        app.log_level = "WARN"
        assert app.log.level == logging.WARN
        app.log.info("Test a")
        captured = capsys.readouterr()
        assert not captured.err
        assert not captured.out

        app.log_level = "INFO"
        assert app.log.level == logging.INFO
        app.log.info("Test b")
        captured = capsys.readouterr()
        assert captured.err == "[INFO]tests.config.test_application.App:: Test b\n"
