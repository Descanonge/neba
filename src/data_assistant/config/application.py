"""Main entry point for configuration."""

from __future__ import annotations

import logging
import sys
import typing as t
from os import path

from traitlets import Bool, List, Unicode, Union
from traitlets.config.configurable import MultipleInstanceError, SingletonConfigurable

from .loaders import CLILoader, ConfigValue
from .section import Section
from .util import ConfigErrorHandler, nest_dict

if t.TYPE_CHECKING:
    from .loaders import ConfigValue, FileLoader

log = logging.getLogger(__name__)

S = t.TypeVar("S", bound=Section)

_SingleS = t.TypeVar("_SingleS", bound="SingletonSection")


class SingletonSection(Section, SingletonConfigurable):
    @classmethod
    def _walk_mro(cls) -> t.Generator[type[SingletonSection], None, None]:
        """Walk the cls.mro() for parent classes that are also singletons.

        For use in instance()
        """
        for parent in cls.mro():
            if (
                issubclass(cls, parent)
                and issubclass(parent, SingletonSection)
                and parent != SingletonSection
            ):
                yield parent


class ApplicationBase(SingletonSection):
    """Base application class.

    Orchestrate the loading of configuration keys from files or from command line
    arguments.
    Pass the combined configuration keys to the appropriate sections in the configuration
    tree structure. This validate the values and instanciate the configuration objects.
    """

    _separate_sections: dict[str, type[Section]] = {}
    """Separate configuration sections."""

    strict_parsing = Bool(
        True,
        help="""\
        If true, raise errors when encountering unknown configuration keys. Otherwise
        only log a warning and keep the illegal key.

        Are concerned only subclasses of :class:`~.util.ConfigError`, and parts of the
        code enclosed in a :class:`~.util.ConfigErrorHandler` context manager.
        """,
    )

    config_files = Union(
        [Unicode(), List(Unicode())],
        default_value=["config.toml"],
        help=(
            "Path to configuration files. Either relative from interpreter "
            "working directory or absolute."
        ),
    )

    auto_instanciate = Bool(
        True,
        help=(
            """
            Instanciate all sections in the configuration tree at application start.

            Instanciation is necessary to fully validate the values of the configuration
            parameters, but in case systematic instanciation is unwanted this can be
            disabled (for example in case of costly instanciations)."""
        ),
    )

    ignore_cli = Bool(False, help="If True, do not parse command line arguments.")

    file_loaders: list[type[FileLoader]] = []
    """List of possible configuration loaders from file, for different formats.

    Each will be tried until an appropriate loader is found. Currently, loaders only
    look at the extension.
    """

    _extra_parameters_args: list[tuple[list, dict[str, t.Any]]] = []
    """Extra parameters passed to the command line parser."""

    @classmethod
    def __init_subclass__(cls, /, **kwargs) -> None:
        # for section in cls.sections:
        #     section._application = cls
        #     name = section.__name__
        #     if hasattr(cls, name):
        #         raise AttributeError(
        #             f"Separate section {name} clashes with existing "
        #             f"attribute in {cls.__name__}"
        #         )
        #     setattr(cls, name, subsection(section))

        super().__init_subclass__(**kwargs)

    def __init__(self, start: bool = True, **kwargs) -> None:
        # No super.__init__, it would instanciate recursively subsections

        # Useless-ish but we need to initialize the logger
        # otherwise it is going to be modified on its first access in __del__
        # which will trigger the logging configuration at a bad time
        self.log.debug("Starting applications")

        self.cli_conf: dict[str, ConfigValue] = {}
        """Configuration values obtained from command line arguments."""
        self.file_conf: dict[str, ConfigValue] = {}
        """Configuration values obtained from configuration files."""

        self.extra_parameters: dict[str, t.Any] = {}
        """Extra parameters retrieved by the command line parser."""

        if start:
            self.start(**kwargs)

    @classmethod
    def register_section(cls, section: type[S]) -> type[S]:
        section._application_cls = cls
        cls._separate_sections[section.__name__] = section
        return section

    def start(
        self,
        argv: list[str] | None = None,
        ignore_cli: bool | None = None,
        instanciate: bool | None = None,
    ) -> None:
        """Initialize and start application.

        - Parse command line arguments (optional)
        - Load configuration file(s)
        - Merge configurations
        - (Re)Apply configuration to Application
        - Instanciate sections objects (optional)

        Instanciation is necessary to fully validate the values of the configuration
        parameters, but in case systematic instanciation is unwanted this can be
        disabled (for example in case of costly instanciations).

        Parameters
        ----------
        argv
            Override command line arguments to parse. If left to None, arguments are
            obtained from :meth:`get_argv`.
        ignore_cli
            If True, do not parse command line arguments. If not None, this argument
            overrides :attr:`ignore_cli`.
        instanciate
            If True, instanciate all sections. If not None, this argument overrides
            :attr:`auto_instanciate`.
        """
        # TODO: Catch errors and silence them if setting is not strict
        # Parse CLI first
        #  -> needed for help, or setting config filenames
        if ignore_cli is None:
            ignore_cli = self.ignore_cli
        if not ignore_cli:
            self.cli_conf = self.parse_command_line(argv)
            log.debug("Found config keys from CLI: %s", ", ".join(self.cli_conf.keys()))

        # Read config files
        if self.config_files:
            self.file_conf = self.load_config_files()

        self.conf = self.merge_configs(self.file_conf, self.cli_conf)

        # Apply config relevant to this instance (only self, not recursive)
        config = nest_dict(self.conf)
        self._init_direct_traits(config)

        if instanciate is None:
            instanciate = self.auto_instanciate
        if instanciate:
            self._init_subsections(config)

    def _create_cli_loader(
        self, argv: list[str] | None, log: logging.Logger | None = None, **kwargs
    ) -> CLILoader:
        """Create a CLILoader instance to parse command line arguments."""
        return CLILoader(self, **kwargs)

    def parse_command_line(
        self, argv: list[str] | None = None, log: logging.Logger | None = None, **kwargs
    ) -> dict[str, ConfigValue]:
        """Return configuration parsed from command line arguments.

        Parameters
        ----------
        argv
            Command line arguments. If None, they are obtained through :meth:`get_argv`.
        kwargs
            Passed to :class:`~.loader.CLILoader` initialization.
        """
        if argv is None:
            argv = self.get_argv()
        loader = self._create_cli_loader(argv, **kwargs)
        for args, kwargs in self._extra_parameters_args:
            action = loader.parser.add_argument(*args, **kwargs)
            self.extra_parameters[action.dest] = action.default
        return loader.get_config(argv)

    def get_argv(self) -> list[str] | None:
        """Return command line arguments.

        Currently return None, which can be passed down to the parser
        :class:`argparse.ArgumentParser`.
        To handle more complex cases, like separating arguments for different
        applications (with ``--`` typically), more logic can be setup here.
        """
        argv = sys.argv[1:]
        if "--" in argv:
            idx = argv.index("--")
            argv = argv[idx + 1 :]
        return argv

    @classmethod
    def add_extra_parameter(cls, *args, **kwargs):
        """Add an extra parameter to the CLI argument parser.

        Extra parameters will be available after CLI parsing in
        :attr:`extra_parameters`.

        Parameters
        ----------
        args, kwargs
            Passed to :meth:`argparse.ArgumentParser.add_argument`.

        """
        cls._extra_parameters_args.append((args, kwargs))

    def load_config_files(self) -> dict[str, ConfigValue]:
        """Return configuration loaded from files."""
        if isinstance(self.config_files, str):
            self.config_files = [self.config_files]

        if not self.config_files:
            return {}

        file_conf = {}
        file_confs: dict[str, dict[str, ConfigValue]] = {}
        for filepath in self.config_files:
            if not path.isfile(filepath):
                continue

            loader_cls = self._select_file_loader(filepath)
            loader = loader_cls(self, filepath)
            file_confs[filepath] = loader.get_config()

        if len(file_confs) == 0:
            log.info("No config files found (%s)", str(self.config_files))
        elif len(file_confs) == 1:
            file_conf = list(file_confs.values())[0]
        else:
            file_conf = self.merge_configs(*file_confs.values())

        return file_conf

    def _select_file_loader(self, filename: str) -> type[FileLoader]:
        """Return the first appropriate FileLoader for this file."""
        select: type[FileLoader] | None = None
        for loader_cls in self.file_loaders:
            if loader_cls.can_load(filename):
                select = loader_cls
                break
        if select is None:
            raise KeyError(
                f"Did not find appropriate loader for config file {filename}. "
                f" Supported loaders are {self.file_loaders}"
            )
        return select

    def resolve_config_value(self, cv: ConfigValue) -> ConfigValue:
        """Resolve all keys in the config and validate it.

        Keys can use aliases/shortcuts, and also be under the form of "class keys"
        ``SectionClassName.trait_name = ...``. We normalize all keys as dot separated
        attributes names, without shortcuts, that point a trait.
        Keys that do not resolve to any known trait will raise error.

        The trait and containing section class will be added to each :class:`ConfigValue`.

        Parameters
        ----------
        config
            Flat mapping of all keys to their ConfigValue

        Returns
        -------
        resolved_config
            Flat mapping of normalized keys to their ConfigValue
        """
        first = cv.path[0]

        separate = first in self._separate_sections
        section = self._separate_sections.get(first, self)

        out = cv.copy()
        # If an error happens in resolve_key, we have a fallback
        fullkey = cv.key
        with ConfigErrorHandler(self, cv.key):
            fullkey, container_cls, trait = section.resolve_key(cv.key)
            out.container_cls = container_cls
            out.trait = trait

        if separate:
            fullkey = f"{first}.{fullkey}"

        out.key = fullkey
        return out

    def write_config(
        self,
        filename: str | None = None,
        comment: str = "full",
        use_current_traits: bool = True,
        clobber: str | None = None,
    ):
        """(Over)write a configuration file.

        Parameters
        ----------
        filename:
            Write to this file. If None, the first filename from :attr:`config_files` is
            used.
        comment:
            Include more or less information in comments. Can be one of:

            * full: all information about traits is included
            * no-help: help string is not included
            * none: no information is included, only the key and default value

            Note that the line containing the key and value, for instance
            ``traitname = 2`` will be commented if the value is equal to the default.
        use_current_traits:
            If True (default), any trait that has a different value from its default one
            will be specified uncommented in the file.
        clobber:
            If the target file already exists, either:

            * abort: the file is left as-is
            * overwrite: the file is completely overwritten with the current
              configuration
            * update: the configuration keys specified in the existing file are kept.
              They take precedence over the current application config. Class-keys are
              not resolved to full-keys.
            * None: ask what to do interactively in the console
        """
        options = dict(u="update", o="overwrite", a="abort")
        default = "a"
        inits = [i.upper() if i == default else i for i in options.keys()]

        # config to write, start with non-default traits
        config: dict[str, ConfigValue] = {}
        if use_current_traits:
            for key, default in self.defaults_recursive(flatten=True).items():
                if (value := self[key]) != default:
                    cv = ConfigValue(value, key)
                    cv.value = value
                    config[key] = cv

        def ask() -> str:
            prompt = (
                ", ".join(f"({i}){options[i.lower()][1:]}" for i in inits)
                + f" [{'/'.join(inits)}]"
            )
            try:
                return input(prompt)[:1].lower() or default
            except KeyboardInterrupt:
                print("")  # empty line
                return default

        if filename is None:
            if isinstance(self.config_files, list | tuple):
                filename = self.config_files[0]
            else:
                filename = self.config_files

        filename = path.realpath(filename)

        loader = self._select_file_loader(filename)(self, filename)

        file_exist = path.exists(filename)
        if file_exist:
            if clobber and clobber not in options.values():
                raise ValueError(
                    f"`clobber` argument must be in {list(options.values())}"
                )
            if not clobber:  # Nothing specified, ask the user interactively
                print(f"Config file already exists '{filename}")

                clobber = ask()
                while clobber not in options:
                    print(f"Please answer one of {'/'.join(options.keys())}")
                    clobber = ask()
                clobber = options[clobber]

            if clobber == "abort":
                return

            log.info(
                "%sing configuration file %s.",
                clobber.title().removesuffix("e"),
                filename,
            )

            if clobber == "update":
                from_file = loader.get_config(
                    apply_application_traits=False, resolve=False
                )
                config = self.merge_configs(config, from_file)

        loader.config = config
        lines = loader.to_lines(comment=comment)

        with open(filename, "w") as f:
            f.write("\n".join(lines))

    def exit(self, exit_status: int | str = 0):
        """Exit python interpreter."""
        sys.exit(exit_status)
