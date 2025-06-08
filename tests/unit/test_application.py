"""Test more integrated features of the Application."""

from data_assistant.config.application import ApplicationBase
from data_assistant.config.loaders.python import PyLoader
from data_assistant.config.loaders.toml import TomlkitLoader

from ..conftest import todo
from ..generic_sections import GenericConfig, GenericConfigInfo


class App(ApplicationBase, GenericConfig):
    file_loaders = [PyLoader, TomlkitLoader]


App.config_files.default_value = ["config.py", "config.toml"]


@todo
def test_logger():
    # test it goes to the correct logger ? idk
    assert 0


@todo
def test_strict_parsing_off():
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
    @todo
    def test_add_extra_parameter(self):
        # check it adds stuff in the right places
        assert 0

    @todo
    def test_extra_parameters_values(self):
        # check we parsed some good values out of it
        assert 0


@todo
def test_resolve_config():
    # normal keys
    # orphan keys
    # aliases
    assert 0


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
