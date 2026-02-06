"""Test loaders and associated functionalities."""

from tempfile import NamedTemporaryFile
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from ruamel.yaml.constructor import DuplicateKeyError
from tomlkit.exceptions import ParseError
from traitlets import Instance, Int, List, TraitType, Unicode, Union

from neba.config.application import ApplicationBase
from neba.config.loaders.core import (
    ConfigLoader,
    ConfigValue,
    DictLoader,
    FileLoader,
)
from neba.config.loaders.python import PyConfigContainer
from neba.config.util import (
    ConfigParsingError,
    MultipleConfigKeyError,
    UnknownConfigKeyError,
)
from tests.config.generic_config import GenericConfig, GenericConfigInfo

LOADERS: list[type[ConfigLoader]]
FILE_LOADERS: list[type[FileLoader]]


allow_fixture = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


@pytest.fixture
def App() -> type[ApplicationBase]:
    class App(ApplicationBase, GenericConfig):
        pass

    App.config_files.default_value = []
    return App


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


class TestDictLoader:
    """Test on python dict."""

    @given(values=GenericConfigInfo.values_strat_nested())
    @allow_fixture
    def test_flat(self, values: tuple[dict, dict], App: type[ApplicationBase]):
        values_nest, values_flat = values

        app: ApplicationBase = App(argv=[], start=False)

        loader = DictLoader(app)
        conf_cv = loader.get_config(values_nest)
        conf = {k: v.get_value() for k, v in conf_cv.items()}
        assert conf == values_flat


class TestCLILoader:
    def test_help(self, App: type[ApplicationBase]):
        with pytest.raises(SystemExit):
            App(argv=["--help"])
        with pytest.raises(SystemExit):
            App(argv=["-h"])

    def test_list_parameters(self, capsys, App: type[ApplicationBase]):
        with pytest.raises(SystemExit):
            App(argv=["--list-parameters"])
        captured = capsys.readouterr()
        listed_parameters = captured.err.splitlines()
        traits = App.traits_recursive(aliases=True, config=True)
        for param in listed_parameters:
            assert param.split()[0].removeprefix("--") in traits
        assert len(traits) == len(listed_parameters)

    def test_parsing(self, App: type[ApplicationBase]):
        args = []
        ref = {}
        for k, (arg, value) in GenericConfigInfo.generic_args().items():
            ref[k] = value
            args.append(f"--{k}")
            args += arg

        args += ["--deep_short.alias_only", "5"]

        app = App(start=False)
        parsed = app.parse_command_line(args)

        parsed = {k: v.get_value() for k, v in parsed.items()}
        assert parsed.pop("deep_sub.sub_generic_deep.alias_only") == 5
        assert ref == parsed

    def test_duplicate_keys(self, App: type[ApplicationBase]):
        with pytest.raises(MultipleConfigKeyError):
            App(argv="--sub-generic.int 1 --sub-generic.int 2".split())

    def test_extra_parameters(self, App: type[ApplicationBase]):
        App.add_extra_parameters(test=Int(0))

        assert "extra" in App._subsections
        app = App(argv=["--extra.test=5"])
        assert "extra.test" in app
        assert app["extra.test"] == 5

    def test_didyoumean(self, App: type[ApplicationBase]):
        with pytest.raises(UnknownConfigKeyError) as excinfo:
            App(argv="--int_ 0 --sub_generic_.int 0 --sub_generic.int_ 0".split())
        assert str(excinfo.value) == (
            "Unrecognized argument(s): "
            "--int_ (did you mean 'int'?), "
            "--sub_generic_.int (did you mean 'sub_generic.int'?), "
            "--sub_generic.int_ (did you mean 'sub_generic.int'?), "
            "use -h/--help or --list-parameters to see available parameters"
        )


class FileLoaderTest:
    ext: str

    convert_set_tuple = True
    comments = False

    def test_reading(self, App: type[ApplicationBase]):
        app = App(start=False)
        app.config_files = f"./tests/config/config{self.ext}"
        conf: dict[str, Any] = app.load_config_files()
        conf = {k: v.get_value() for k, v in conf.items()}

        ref = {k: v[1] for k, v in GenericConfigInfo.generic_args().items()}
        # deal with alias resolution separately
        ref["deep_sub.sub_generic_deep.alias_only"] = 5

        if self.convert_set_tuple:
            # toml, yaml, json only outputs lists so here we convert them
            # Traitlets does this otherwise but here we check the conf dict directly
            conf = {
                k: tuple(v) if isinstance(ref[k], tuple) else v for k, v in conf.items()
            }
            conf = {
                k: set(v) if isinstance(ref[k], set) else v for k, v in conf.items()
            }

        assert conf == ref

    @given(values=GenericConfigInfo.values_all_strat())
    @allow_fixture
    def test_write_and_read_all(self, values: dict, App: type[ApplicationBase]):
        self.assert_write_read(values, App)

    @given(values=GenericConfigInfo.values_half_strat())
    @allow_fixture
    def test_write_and_read_half(self, values: dict, App: type[ApplicationBase]):
        self.assert_write_read(values, App)

    def assert_write_read(self, values: dict, App: type[ApplicationBase]):
        app = App(argv=[])
        traits = app.traits_recursive()
        defaults = app.defaults_recursive()

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

        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            app.write_config(filename, clobber="overwrite", comment=self.comments)

            App.config_files = [filename]
            app = App(argv=[])

        for k in ref:
            assert app[k] == values[k]


class TestTomlLoader(FileLoaderTest):
    ext = ".toml"
    comments = True

    def test_duplicate_keys(self, App: type[ApplicationBase]):
        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            with open(filename, "w") as fp:
                print("bool = false", file=fp)
                print("bool = true", file=fp)

            App.config_files = [filename]

            with pytest.raises(ParseError):
                App(ignore_cli=True)

    def test_didyoumean(self, App: type[ApplicationBase]):
        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            with open(filename, "w") as fp:
                print("int_ = 0", file=fp)

            App.config_files = [filename]

            with pytest.raises(UnknownConfigKeyError) as excinfo:
                App(ignore_cli=True)
                assert "Did you mean 'int'?" in str(excinfo.value)


class TestPythonLoader(FileLoaderTest):
    ext = ".py"
    convert_set_tuple = False
    comments = True

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

    def test_exception(self, App: type[ApplicationBase]):
        """Test when file throw exception."""
        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            with open(filename, "w") as fp:
                print("c.bool = undefined_var", file=fp)

            App.config_files = [filename]

            with pytest.raises(ConfigParsingError):
                App(ignore_cli=True)

    def test_duplicate_keys(self, App: type[ApplicationBase]):
        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            with open(filename, "w") as fp:
                print("c.bool = False", file=fp)
                print("c.bool = True", file=fp)

            App.config_files = [filename]

            with pytest.raises(ConfigParsingError):
                App(ignore_cli=True)


class TestYamlLoader(FileLoaderTest):
    ext = ".yaml"
    comments = True

    def test_duplicate_keys(self, App: type[ApplicationBase]):
        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            with open(filename, "w") as fp:
                print("bool: False", file=fp)
                print("bool: True", file=fp)

            App.config_files = [filename]

            with pytest.raises(DuplicateKeyError):
                App(ignore_cli=True)


class TestJsonLoader(FileLoaderTest):
    ext = ".json"

    def test_duplicate_keys(self, App: type[ApplicationBase]):
        with NamedTemporaryFile(suffix=self.ext) as conf_file:
            filename = conf_file.name
            with open(filename, "w") as fp:
                print('{"bool": false, "bool": true}', file=fp)

            App.config_files = [filename]

            with pytest.raises(MultipleConfigKeyError):
                App(ignore_cli=True)


def test_config_merge(App):
    """Test config from different sources get merged properly.

    Ordered (in increasing priority) as Py, Toml, CLI.

    - int: Defined in Py => value from Py
    - bool: Defined in Toml => value from Toml
    - float: Defined in CLI => value from CLI
    - str: Defined in Py, CLI => value from CLI
    - enum_int: Defined in Toml, CLI => value from CLI
    - enum_str: Defined in Py, Toml => value from Toml
    - enum_mix: Defined in Py, Toml, CLI => value from CLI

    Same thing in a subsection
    """
    with (
        NamedTemporaryFile(suffix=".toml") as conf_file_toml,
        NamedTemporaryFile(suffix=".py") as conf_file_py,
    ):
        toml_filename = conf_file_toml.name
        py_filename = conf_file_py.name
        with open(toml_filename, "w") as fp:
            print("bool = true", file=fp)
            print("enum_int = 1", file=fp)
            print("enum_str = 'b'", file=fp)
            print("enum_mix = 2", file=fp)

            print("[sub_generic]", file=fp)
            print("bool = true", file=fp)
            print("enum_int = 1", file=fp)
            print("enum_str = 'b'", file=fp)
            print("enum_mix = 2", file=fp)

        with open(py_filename, "w") as fp:
            print("c.int = 1", file=fp)
            print("c.str = 'a'", file=fp)
            print("c.enum_str = 'a'", file=fp)
            print("c.enum_mix = 1", file=fp)

            print("c.sub_generic.int = 1", file=fp)
            print("c.sub_generic.str = 'a'", file=fp)
            print("c.sub_generic.enum_str = 'a'", file=fp)
            print("c.sub_generic.enum_mix = 1", file=fp)

        argv = [
            "--float=1.0",
            "--str=b",
            "--enum_int=2",
            "--enum_mix=3",
            "--sub_generic.float=1.0",
            "--sub_generic.str=b",
            "--sub_generic.enum_int=2",
            "--sub_generic.enum_mix=3",
        ]

        App.config_files = [py_filename, toml_filename]
        app = App(argv=argv)

        def check_cv(key: str, value: Any, origin: str):
            cv = app.conf[key]
            assert cv.get_value() == value
            assert cv.origin == origin

        check_cv("int", 1, py_filename)
        check_cv("bool", True, toml_filename)
        check_cv("float", 1.0, "CLI")
        check_cv("str", "b", "CLI")
        check_cv("enum_int", 2, "CLI")
        check_cv("enum_str", "b", toml_filename)

        check_cv("sub_generic.int", 1, py_filename)
        check_cv("sub_generic.bool", True, toml_filename)
        check_cv("sub_generic.float", 1.0, "CLI")
        check_cv("sub_generic.str", "b", "CLI")
        check_cv("sub_generic.enum_int", 2, "CLI")
        check_cv("sub_generic.enum_str", "b", toml_filename)
