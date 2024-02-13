import logging
from collections.abc import Callable
from os import path

from traitlets import Bool, Instance, List, TraitType, Unicode, Union
from traitlets.config import Application, Configurable

from .loader import (
    CLILoader,
    ConfigKV,
    ConfigLoader,
    FileLoader,
    NestedKVType,
    PyLoader,
    TomlLoader,
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
        default_value="config.py",
        help="Load those config files.",
    )

    file_loaders: list[type[FileLoader]] = [TomlLoader, YamlLoader, PyLoader]

    def __init__(self, *args, **kwargs) -> None:
        self.cli_conf: NestedKVType = {}
        self.file_conf: NestedKVType = {}

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

    @property
    def classes(self):
        return self._classes_inc_parents()

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

        # Read config files
        # Sets self.config
        if self.config_files:
            self.load_config_files()

        self.conf = self.file_conf | self.cli_conf

        self.instanciate_subschemes()

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
        loader = self._create_cli_loader(argv, log=log, **kwargs)
        self.cli_conf = loader.load_config()

    def load_config_files(self, log: logging.Logger | None = None) -> NestedKVType:
        if log is None:
            log = self.log
        if isinstance(self.config_files, str):
            self.config_files = [self.config_files]

        file_confs: dict[str, NestedKVType] = {}
        for filepath in self.config_files:
            _, ext = path.splitext(filepath)

            found_loader = False
            for loader_cls in self.file_loaders:
                if ext.lstrip(".") in loader_cls.extensions:
                    found_loader = True
                    loader = loader_cls(filepath, self, log=log)
                    file_confs[filepath] = loader.load_config()
                    break

            if not found_loader:
                raise KeyError(
                    f"Did not find loader for config file {filepath}. "
                    f" Supported loaders are {self.file_loaders}"
                )

        return self.merge_configs(*file_confs.values())

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
                idx = [cls.__name__ for cls in self.classes].index(dest)
                dest = self.classes[idx]

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
            filename = self.config_file

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

    def merge_configs(
        self,
        *configs: NestedKVType,
    ) -> NestedKVType:
        out: NestedKVType = {}
        for c in configs:
            for k, v in c.items():
                if isinstance(v, ConfigKV):
                    if k in out:
                        self.log.debug("overwrite")
                    out[k] = v
                else:
                    configs_lower = [c[k] for c in configs]
                    out[k] = self.merge_configs(*configs_lower)  # type:ignore

        return out

    def _filter_parent_app(self, classes):
        for c in classes:
            if issubclass(c, Application) and c != self.__class__:
                continue
            yield c

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
