import logging
import sys
from collections.abc import Callable, Iterator
from os import path

from traitlets import Bool, Instance, List, TraitType, Unicode, Union
from traitlets.config import Application, Configurable

from .loader import (
    CLILoader,
    ConfigDict,
    ConfigLoader,
    FileLoader,
    PyLoader,
    TomlKitLoader,
    YamlLoader,
)
from .scheme import Scheme


class ApplicationBase(Scheme):
    """Base application class.

    Manages loading config from files and CLI.
    """

    strict_parsing = Bool(
        True,
        help=(
            "If true, raise errors when encountering unknown "
            "arguments or configuration keys. Else only prints "
            "a warning."
        ),
    )

    config_files = Union(
        [Unicode(), List(Unicode())],
        default_value="config.toml",
        help="Load those config files.",
    )

    file_loaders: list[type[FileLoader]] = [TomlKitLoader, YamlLoader, PyLoader]

    def __init__(self, *args, **kwargs) -> None:
        self.cli_conf = ConfigDict()
        self.file_conf = ConfigDict()

        self.log = logging.getLogger(__name__)

    @classmethod
    def add_scheme(cls) -> Callable[[type[Configurable]], type[Configurable]]:
        """Decorate a Configurable to make it available to configuration.

        Useful for schemes that are not explicitely specified in the configuration
        structure.
        They will be set as an Instance trait to the application, accessible with the
        name of the class.
        """

        def decorator(conf: type[Configurable]) -> type[Configurable]:
            trait = Instance(klass=conf, args=(), kwargs={}).tag(config=True)
            setattr(cls, conf.__name__, trait)
            return conf

        return decorator

    def initialize(self, argv=None, ignore_cli: bool = False, instanciate: bool = True):
        """Initialize application.

        - Parse command line arguments.
        - Load configuration file.
        - Instanciate schemes

        Parameters
        ----------
        argv:
            If not None override command line arguments.
        ignore_cli:
            If True, do not parse command line arguments. Useful
            for jupyter notebooks for instance.
        """
        # First parse CLI
        # needed for help, or overriding the config files)
        # Sets self.cli_conf
        if not ignore_cli:
            self.parse_command_line(argv)

        self.apply_cli_config()

        # Read config files
        # Sets self.file_conf
        if self.config_files:
            self.load_config_files()

        self.conf = self.merge_configs(self.file_conf, self.cli_conf)

        self.instanciate_subschemes(self.conf.to_nested_dict())

    def _create_cli_loader(
        self,
        argv: list[str] | None,
        log: logging.Logger | None = None,
    ) -> ConfigLoader:
        if log is None:
            log = self.log
        return CLILoader(self, log=log)

    def parse_command_line(
        self, argv=None, log: logging.Logger | None = None, **kwargs
    ):
        # argv handling should go here in case we want something fancier
        # At the moment we pass None down to ArgumentParser
        loader = self._create_cli_loader(argv, log=log, **kwargs)
        self.cli_conf = loader.get_config()

    def apply_cli_config(self) -> None:
        for kv in self.cli_conf.values():
            if kv.container_cls is not None and isinstance(self, kv.container_cls):
                setattr(self, kv.lastname, kv.value)

    def load_config_files(self, log: logging.Logger | None = None):
        if log is None:
            log = self.log
        if isinstance(self.config_files, str):
            self.config_files = [self.config_files]

        file_confs: dict[str, ConfigDict] = {}
        for filepath in self.config_files:
            _, ext = path.splitext(filepath)

            found_loader = False
            for loader_cls in self.file_loaders:
                if ext.lstrip(".") in loader_cls.extensions:
                    found_loader = True
                    loader = loader_cls(filepath, self, log=log)
                    file_confs[filepath] = loader.get_config()
                    break

            if not found_loader:
                raise KeyError(
                    f"Did not find loader for config file {filepath}. "
                    f" Supported loaders are {self.file_loaders}"
                )

        if len(file_confs) > 1:
            self.file_conf = self.merge_configs(*file_confs.values())
        else:
            self.file_conf = list(file_confs.values())[0]

    def add_extra_parameter(
        self,
        name: str,
        trait: TraitType,
        dest: type[Configurable] | str | None = None,
        auto_alias: bool = True,
    ):
        """Add a configurable trait to this application configuration.

        Parameters
        ----------
        name:
            Name of the trait.
        trait:
            Trait object to add. It will automatically be tagged as configurable.
            It will be accessible in the config object, under `dest`.
        dest:
            Subclass of :class:`Configurable` that will host the trait (one of
            :attr:`classes` typically). If left to None, it will default to this
            class. If specified as a string, it should correspond to the name
            of a class present in ``App.classes``.
        auto_alias:
            If True (default), it will automatically add an alias so that the
            trait can be set directly with ``--{name}=`` instead of
            ``--{dest}.{name}=``.
        """
        if dest is None:
            dest = self.__class__
        elif isinstance(dest, str):
            if dest in self._subschemes:
                dest = self._subschemes[dest]
            else:
                classes = {cls.__name__: cls for cls in self._classes_inc_parents()}
                dest = classes[dest]

        trait.tag(config=True)
        setattr(dest, name, trait)
        dest.setup_class(dest.__dict__)  # type: ignore

    def write_config(
        self,
        filename: str | None = None,
        comment: bool = True,
        ask_overwrite: bool = True,
    ):
        """(Over)write a configuration file.

        Parameters
        ----------
        filename:
            Write to this file. If None, the current value of
            :attr:`config_file` is used.
        comment:
            If True (default), comment configuration lines.
        ask_overwrite:
            If True (default), ask for confirmation if config file
            already exists. Else, overwrite the file without questions.
        """
        if filename is None:
            if isinstance(self.config_files, list | tuple):
                filename = self.config_files[0]
            else:
                filename = self.config_files

        filename = path.realpath(filename)

        if path.exists(filename) and ask_overwrite:
            print(f"Config file already exists '{filename}")

            def ask():
                prompt = "Overwrite with new config? [y/N]"
                try:
                    return input(prompt).lower() or "n"
                except KeyboardInterrupt:
                    print("")  # empty line
                    return "n"

            answer = ask()
            while not answer.startswith(("y", "n")):
                print("Please answer 'yes' or 'no'")
                answer = ask()
            if answer.startswith("n"):
                return

        lines = self.generate_config_file().splitlines()

        # Remove trailing whitespace
        lines = [line.rstrip() for line in lines]

        if not comment:
            for i, line in enumerate(lines):
                if line.startswith("# c."):
                    lines[i] = line.removeprefix("# ")

        with open(filename, "w") as f:
            f.write("\n".join(lines))

    def _filter_parent_app(self, classes):
        for c in classes:
            if issubclass(c, Application) and c != self.__class__:
                continue
            yield c

    def emit_help(self) -> Iterator[str]:
        yield "lol"

    def exit(self, exit_status: int | str = 0):
        sys.exit(exit_status)

    def generate_config_file(self, classes=None):
        """Generate default config file from Configurables.

        Override to avoid documenting base classes of the application.
        """
        lines = ["# Configuration file for %s." % self.name]
        lines.append("")
        lines.append("c = get_config()  #" + "noqa")
        lines.append("")
        classes = self.classes if classes is None else classes
        config_classes = list(self._classes_with_config_traits(classes))
        config_classes = self._filter_parent_app(config_classes)
        for cls in config_classes:
            lines.append(cls.class_config_section(config_classes))

        return "\n".join(lines)
