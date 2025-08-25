"""Test more integrated features of the Application."""

import pytest
from hypothesis import given
from traitlets import Float, Int

from data_assistant.config.application import ApplicationBase
from data_assistant.config.loaders import ConfigValue, FileLoader
from data_assistant.config.loaders.json import JsonLoader
from data_assistant.config.loaders.python import PyLoader
from data_assistant.config.loaders.toml import TomlkitLoader
from tests.config.generic_config import GenericConfig, GenericConfigInfo
from tests.conftest import todo


class App(ApplicationBase, GenericConfig):
    file_loaders = [PyLoader, TomlkitLoader, JsonLoader]


App.config_files.default_value = ["config.py", "config.toml"]


@todo
def test_logger():
    # test it goes to the correct logger ? idk
    assert 0


@todo
def test_strict_parsing_off():
    assert 0


@given(values=GenericConfigInfo.values_strat())
def test_orphan(values: dict):
    class AppWithOrphan(ApplicationBase):
        pass

    section_cls = AppWithOrphan.register_orphan(GenericConfig)

    app = AppWithOrphan(start=False)
    app.conf = {"GenericConfig." + k: ConfigValue(v, k) for k, v in values.items()}

    section = section_cls.from_app(app)
    for k, v in values.items():
        assert section[k] == v


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


def test_resolve_orphan_config():
    class AppWithOrphan(ApplicationBase):
        pass

    section_cls = AppWithOrphan.register_orphan(GenericConfig)

    app = AppWithOrphan(start=False)
    app._init_subsections({})

    cv = ConfigValue(2, "GenericConfig.int")
    out = app.resolve_config_value(cv)
    assert out.input == 2
    assert out.key == "GenericConfig.int"
    assert out.trait is section_cls.int
    assert out.container_cls is section_cls

    cv = ConfigValue(3, "GenericConfig.deep_sub.sub_generic_deep.int")
    out = app.resolve_config_value(cv)
    assert out.input == 3
    assert out.key == "GenericConfig.deep_sub.sub_generic_deep.int"
    assert out.trait is section_cls.int
    assert (
        out.container_cls
        is section_cls._subsections["deep_sub"]._subsections["sub_generic_deep"]
    )

    # aliases
    cv = ConfigValue(4, "GenericConfig.deep_short.int")
    out = app.resolve_config_value(cv)
    assert out.input == 4
    assert out.key == "GenericConfig.deep_sub.sub_generic_deep.int"
    assert (
        out.trait
        is section_cls._subsections["deep_sub"]._subsections["sub_generic_deep"].int
    )
    assert (
        out.container_cls
        is section_cls._subsections["deep_sub"]._subsections["sub_generic_deep"]
    )


class TestWriteConfig:
    # parmetrize for multiple loaders
    @todo
    def test_write_no_comment(self):
        # check no comments in output
        assert 0

    @todo
    def test_clobber_abort(self):
        assert 0

    @todo
    def test_clobber_overwriter(self):
        assert 0

    @todo
    def test_clobber_update(self):
        assert 0

    @todo
    def test_clobber_ask(self):
        # How do you test this ?
        assert 0
