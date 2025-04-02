"""Test loaders and associated functionalities."""

from tempfile import NamedTemporaryFile

import pytest
from hypothesis import given
from traitlets import Instance, Int, List, TraitType, Type, Unicode, Union

from data_assistant.config.application import ApplicationBase
from data_assistant.config.loaders.cli import CLILoader
from data_assistant.config.loaders.core import (
    ConfigLoader,
    ConfigValue,
    DictLoader,
    FileLoader,
)
from data_assistant.config.loaders.python import PyConfigContainer, PyLoader
from data_assistant.config.loaders.toml import TomlkitLoader
from data_assistant.config.util import ConfigParsingError, MultipleConfigKeyError

from ..conftest import todo

# from data_assistant.config.loaders.python import PyLoader
from ..generic_sections import GenericConfig, GenericConfigInfo

LOADERS: list[type[ConfigLoader]]
FILE_LOADERS: list[type[FileLoader]]


class App(ApplicationBase, GenericConfig):
    file_loaders = [PyLoader, TomlkitLoader]


App.config_files.default_value = []


class TestConfigValue:
    """Test ConfigValue related features."""

    def test_copy(self):
        original = ConfigValue([0, 1], "original_key", origin="CLI")
        original.priority = 70

        # test it's identical
        c1 = original.copy()
        for attr in ["input", "key", "origin", "value", "priority"]:
            assert getattr(c1, attr) == getattr(original, attr)

        # test it's a deep copy
        original.input[0] = 5
        assert c1.input == [0, 1]

    def test_get_value(self):
        cv = ConfigValue("0", "")
        assert cv.get_value() == "0"
        cv.value = 1
        assert cv.get_value() == 1

    def test_parse_no_trait(self):
        """Test parsing to a trait."""
        cv = ConfigValue("0", "")
        with pytest.raises(ConfigParsingError):
            cv.parse()

    def assert_parse(self, trait: TraitType, input, value):
        cv = ConfigValue(input, "")
        cv.trait = trait
        cv.parse()
        assert cv.value == value

    def test_parse_simple(self):
        self.assert_parse(Int(), "0", 0)
        self.assert_parse(Int(), ["1"], 1)

        # wrong input
        cv = ConfigValue("a", "")
        cv.trait = Int()
        with pytest.raises(ConfigParsingError):
            cv.parse()

    def test_parse_list(self):
        self.assert_parse(List(Int()), ["0", "1"], [0, 1])

    def test_parse_union(self):
        # simple union
        trait = Union([Int(), Unicode()])
        self.assert_parse(trait, "0", 0)
        self.assert_parse(trait, "a", "a")

        # nested union/list
        trait = Union([Int(), List(Int())])
        self.assert_parse(trait, ["0"], 0)
        self.assert_parse(trait, ["0", "1"], [0, 1])

        self.assert_parse(Union([List(Int()), Int()]), "0", [0])

        trait = Union([Int(), List(Union([Int(), Unicode()]))])
        self.assert_parse(trait, ["0"], 0)
        self.assert_parse(trait, ["0", "1"], [0, 1])
        self.assert_parse(trait, ["a", "b"], ["a", "b"])
        self.assert_parse(trait, ["0", "a"], [0, "a"])

    @todo
    def test_aliases(self):
        assert 0


class TestDictLoader:
    """Test on python dict."""

    @given(values=GenericConfigInfo.values_strat_nested())
    def test_flat(self, values: tuple[dict, dict]):
        values_nest, values_flat = values

        app = App(argv=[], start=False)
        app._init_subsections({})

        loader = DictLoader(app)
        conf_cv = loader.get_config(values_nest)
        conf = {k: v.get_value() for k, v in conf_cv.items()}
        assert conf == values_flat


class TestCLILoader:
    def test_help(self):
        with pytest.raises(SystemExit):
            App(argv=["--help"])
        with pytest.raises(SystemExit):
            App(argv=["-h"])

    def test_list_parameters(self, capsys):
        with pytest.raises(SystemExit):
            App(argv=["--list-parameters"])
        captured = capsys.readouterr()
        listed_parameters = captured.err.splitlines()
        traits = App.class_traits_recursive(subsections=False, aliases=True)
        for param in listed_parameters:
            assert param.split()[0].removeprefix("--") in traits
        assert len(traits) == len(listed_parameters)

    def test_parsing(self):
        args = []
        ref = {}
        for k, (arg, value) in GenericConfigInfo.generic_args().items():
            ref[k] = value
            args.append(f"--{k}")
            args += arg

        app = App(start=False)
        parsed = app.parse_command_line(args)

        parsed = {k: v.get_value() for k, v in parsed.items()}
        assert ref == parsed

    def test_duplicate_keys(self):
        with pytest.raises(MultipleConfigKeyError):
            App(argv="--sub-generic.int 1 --sub-generic.int 2".split())

    @todo
    def test_orphans(self):
        pass


@todo
def test_file_choose_loader():
    # maybe in application ?
    assert 0


class TestTomlLoader:
    def test_reading(self):
        app = App(start=False)
        app.config_files = "./tests/unit/config.toml"
        conf = app.load_config_files()
        conf = {k: v.get_value() for k, v in conf.items()}

        # toml only outputs lists so here we convert them
        # Traitlets does this otherwise
        ref = {k: v[1] for k, v in GenericConfigInfo.generic_args().items()}
        conf = {
            k: tuple(v) if isinstance(ref[k], tuple) else v for k, v in conf.items()
        }
        conf = {k: set(v) if isinstance(ref[k], set) else v for k, v in conf.items()}

        assert conf == ref

    @given(values=GenericConfigInfo.values_half_strat())
    def test_write_and_read_half(self, values: dict):
        self.assert_write_read(values)

    @given(values=GenericConfigInfo.values_all_strat())
    def test_write_and_read_all(self, values: dict):
        self.assert_write_read(values)

    def assert_write_read(self, values: dict):
        app = App(argv=[])
        traits = app.traits_recursive(flatten=True)
        defaults = app.defaults_recursive(flatten=True)

        # Modify values and store them
        ref = {}
        for k, v in values.items():
            # Instances/Types must be imported in config file, not automatic yet
            if type(traits[k]) in [Instance]:
                continue
            # ignore thoses equal as default values, they will not be written
            if v == defaults[k]:
                continue

            app[k] = v
            ref[k] = v

        with NamedTemporaryFile(suffix=".toml") as conf_file:
            filename = conf_file.name
            app.write_config(filename, clobber="overwrite", comment="none")

            App.config_files = [filename]
            app = App(argv=[])

        for k in ref:
            assert app[k] == values[k]

    @todo
    def test_duplicate_keys(self):
        assert 0


class TestPythonLoader:
    """Test loading from executing python file."""

    def test_pyconfig_container(self):
        """Test behavior of the `c` container object."""
        c = PyConfigContainer()
        c.a1 = 1
        c.a2.b1 = 2
        c.a2.b2 = 3
        c.a2.b3.c1 = 4
        c.a3.b1.c1 = 5

        ref = {
            "a1": 1,
            "a2.b1": 2,
            "a2.b2": 3,
            "a2.b3.c1": 4,
            "a3.b1.c1": 5,
        }

        assert c.as_flat_dict() == ref

    @todo
    def test_exception(self):
        """Test when file throw exception."""
        assert 0

    def test_reading(self):
        app = App(argv=[])
        app.config_files = "./tests/unit/config.py"
        conf = app.load_config_files()
        conf = {k: v.get_value() for k, v in conf.items()}

        ref = {k: v[1] for k, v in GenericConfigInfo.generic_args().items()}

        assert conf == ref

    @given(values=GenericConfigInfo.values_half_strat())
    def test_write_and_read_half(self, values: dict):
        self.assert_write_read(values)

    @given(values=GenericConfigInfo.values_all_strat())
    def test_write_and_read_all(self, values: dict):
        self.assert_write_read(values)

    def assert_write_read(self, values: dict):
        app = App(argv=[])
        traits = app.traits_recursive(flatten=True)
        defaults = app.defaults_recursive(flatten=True)
        ref = {}
        for k, v in values.items():
            # Instances/Types must be imported in config file, not automatic yet
            if type(traits[k]) in [Instance]:
                continue
            if v == defaults[k]:
                continue
            ref[k] = v
            app[k] = v

        with NamedTemporaryFile(suffix=".py") as conf_file:
            filename = conf_file.name
            app.write_config(filename, clobber="overwrite", comment="none")

            for line in conf_file.readlines():
                print(line)

            App.config_files = [filename]
            app = App(argv=[])

        for k in ref:
            assert app[k] == values[k]

    @todo
    def test_duplicate_keys(self):
        assert 0


# Parametrize for all loaders
class TestConfigLoader:
    @todo
    def test_application_traits(self):
        """Check application traits are applied."""
        assert 0


# Parametrize for all file loaders
@todo
def test_reading():
    """Test reading a configuration file.

    File is written by hand to change some values from default.
    """
    assert 0


# Parametrize for all file loaders
@todo
def test_to_lines_some():
    # for the typical section
    # change SOME values
    # to_lines in a temp file
    # read file
    # check same values
    assert 0


# Parametrize for all file loaders
@todo
def test_to_lines_all():
    # for the typical section
    # specify ALL values
    # to_lines in a temp file
    # read file
    # check same values
    assert 0
