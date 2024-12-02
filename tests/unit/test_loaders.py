"""Test loaders and associated functionalities."""

from tempfile import NamedTemporaryFile

import pytest
from hypothesis import given
from traitlets import Instance, Int, List, TraitType, Type, Unicode, Union

from data_assistant.config.application import ApplicationBase
from data_assistant.config.loaders.core import ConfigLoader, ConfigValue, FileLoader
from data_assistant.config.loaders.python import PyLoader
from data_assistant.config.util import ConfigParsingError

# from data_assistant.config.loaders.python import PyLoader
from ..scheme_generation import GenericScheme, GenericSchemeInfo

LOADERS: list[type[ConfigLoader]]
FILE_LOADERS: list[type[FileLoader]]


class App(ApplicationBase, GenericScheme):
    file_loaders = [PyLoader]
    pass


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

    def test_aliases(self):
        assert 0


class DictLikeLoader:
    """Test on python dict.

    This behavior should be the same for other loaders (json, yaml) but easier to test.
    """

    def test_reading(self):
        assert 0


class TestCLILoader:
    def test_setting_new_action(self):
        assert 0

    def test_help(self):
        assert 0

    def test_parsing(self):
        args = []
        for k, v in GenericSchemeInfo.generic_args().items():
            args.append(f"--{k}")
            args += v

        app = App()
        parsed = app.parse_command_line(args)

        parsed = {k: v.get_value() for k, v in parsed.items()}
        assert GenericSchemeInfo().generic_values() == parsed

    def test_classkey(self):
        args = "--App.int 15 --GenericTraits.list_int 1 2 --TwinSubscheme.int 3"
        app = App()
        parsed = app.parse_command_line(args.split(" "))
        parsed = {k: v.get_value() for k, v in parsed.items()}

        # --App.int 15
        assert parsed["int"] == 15
        # without effect on GenericTraits
        assert "sub_generic.int" not in parsed

        # --GenericTraits.list_int 1 2
        assert parsed["sub_generic.list_int"] == [1, 2]
        assert parsed["deep_sub.sub_generic_deep.list_int"] == [1, 2]
        # without effect on App
        assert "list_int" not in parsed
        assert app.list_int == [0]

        # --TwinSubscheme.int 3
        assert parsed["twin_a.int"] == 3
        assert parsed["twin_b.int"] == 3
        assert parsed["sub_twin.twin_c.int"] == 3


def test_file_choose_loader():
    # maybe in application ?
    pass


class TestPythonLoader:
    """Test loading from executing python file."""

    def test_pyconfig_container(self):
        """Test behavior of the `c` container object."""
        pass

    def test_exception(self):
        """Test when file throw exception."""
        pass

    def test_reading(self):
        app = App()
        app.config_files = "./tests/unit/config.py"
        conf = app.load_config_files()
        conf = {k: v.get_value() for k, v in conf.items()}

        assert conf == GenericSchemeInfo.generic_values()

    @given(values=GenericSchemeInfo.values_half_strat())
    def test_write_and_read_half(self, values: dict):
        self.assert_write_read(values)

    @given(values=GenericSchemeInfo.values_all_strat())
    def test_write_and_read_all(self, values: dict):
        self.assert_write_read(values)

    def assert_write_read(self, values: dict):
        app = App()
        traits = app.traits_recursive(flatten=True)
        defaults = app.defaults_recursive(flatten=True)
        ref = {}
        for k, v in values.items():
            # Instances/Types must be imported in config file, not automatic yet
            if type(traits[k]) in [Instance, Type]:
                continue
            if v == defaults[k]:
                continue
            ref[k] = v
            app[k] = v

        with NamedTemporaryFile(suffix=".py") as conf_file:
            # filename = conf_file.name
            filename = "tmp_config.py"
            app.write_config(filename, clobber="overwrite", comment="none")

            for line in conf_file.readlines():
                print(line)

            app = App()
            app.config_files = filename
            conf = app.load_config_files()

        conf = {k: v.get_value() for k, v in conf.items()}

        assert conf == ref


# Parametrize for all loaders
class TestConfigLoader:
    def test_add_multiple(self):
        """Key already in config."""
        pass

    def test_application_traits(self):
        """Check application traits are applied."""
        pass


# Parametrize for all file loaders
def test_reading():
    """Test reading a configuration file.

    File is written by hand to change some values from default.
    """
    pass


# Parametrize for all file loaders
def test_to_lines_some():
    # for the typical scheme
    # change SOME values
    # to_lines in a temp file
    # read file
    # check same values
    pass


# Parametrize for all file loaders
def test_to_lines_all():
    # for the typical scheme
    # specify ALL values
    # to_lines in a temp file
    # read file
    # check same values
    pass
