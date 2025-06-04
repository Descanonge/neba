"""Main entry point for configuration."""

from __future__ import annotations

import logging
import sys
import typing as t
from collections.abc import Callable
from os import path

from traitlets import Bool, Bunch, Enum, Int, List, Unicode, Union, default, observe
from traitlets.config.configurable import LoggingConfigurable

from .loaders import CLILoader, ConfigValue
from .section import Section
from .util import ConfigErrorHandler

if t.TYPE_CHECKING:
    from .loaders import ConfigValue, FileLoader

log = logging.getLogger(__name__)

S = t.TypeVar("S", bound=Section)


class ApplicationBase(Section, LoggingConfigurable):
    """Base application class.

    Orchestrate the loading of configuration keys from files or from command line
    arguments.
    Pass the combined configuration keys to the appropriate sections in the configuration
    tree structure. This validate the values and instanciate the configuration objects.

    This is a singleton, only one instance is allowed. See :class:`SingletonSection` for
    details.
    """

    _shared_instance: t.Self
    """Shared instance created/accessed by :meth:`shared`."""

    _orphaned_sections: dict[str, type[Section]] = {}
    """Orphaned configuration sections."""

    file_loaders: list[type[FileLoader]] = []
    """List of possible configuration loaders from file, for different formats.

    Each will be tried until an appropriate loader is found. Currently, loaders only
    look at the extension.
    """
    # -- Config --

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

    # -- Log config --

    log_level = Union(
        [Enum(("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")), Int()],
        default_value="INFO",
        help="Set the log level by value or name.",
    )

    log_datefmt = Unicode(
        "%Y-%m-%d %H:%M:%S",
        help="The date format used by logging formatters for %(asctime)s",
    )

    log_format = Unicode(
        "[%(levelname)s]%(name)s:: %(message)s",
        help="The Logging format template",
    )

    _logging_configured: bool = False

    def _get_logging_config(self) -> dict:
        """Return dictionary config for logging.

        See :func:`logging.config.dictConfig`.

        Whenever the relevant traits or the logger are modified, callbacks events will
        use this method to create a configuration dict. It can be overriden in your
        application class to modify the logging configuration further.
        """
        config = {
            "version": 1,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "stream": "ext://sys.stderr",
                },
            },
            "formatters": {
                "console": {
                    "format": self.log_format,
                    "datefmt": self.log_datefmt,
                },
            },
            "loggers": {
                f"{self.__class__.__module__}.{self.__class__.__name__}": {
                    "level": logging.getLevelName(self.log_level),
                    "handlers": ["console"],
                }
            },
            "disable_existing_loggers": False,
        }

        return config

    @observe("log_format", "log_datefmt", "log_level")
    def _observe_log_format_change(self, change: Bunch) -> None:
        self._configure_logging()

    @observe("log", type="default")
    def _observe_log_default(self, change: Bunch) -> None:
        self._configure_logging()

    def _configure_logging(self) -> None:
        config = self._get_logging_config()
        logging.config.dictConfig(config)
        self._logging_configured = True

    @default("log")
    def _log_default(self) -> logging.Logger:
        return logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    # -- Instance attributes --

    conf: dict[str, ConfigValue]
    """Configuration values obtained from command line arguments and configuration
    files."""
    cli_conf: dict[str, ConfigValue]
    """Configuration values obtained from command line arguments."""
    file_conf: dict[str, ConfigValue]
    """Configuration values obtained from configuration files."""
    extra_parameters: dict[str, t.Any]
    """Extra parameters retrieved by the command line parser."""
    _extra_parameters_args: list[tuple[list, dict[str, t.Any]]]
    """Extra parameters passed to the command line parser."""

    def __init__(self, /, start: bool = True, **kwargs) -> None:
        # No super.__init__, it would instanciate recursively subsections

        self.conf = {}
        self.cli_conf = {}
        self.file_conf = {}
        self.extra_parameters = {}
        self._extra_parameters_args = []

        if start:
            self.start(**kwargs)

    @classmethod
    def shared(cls, *args, new_shared: bool = False, **kwargs) -> t.Self:
        """Return shared instance if existing, otherwise a new instance.

        Parameters
        ----------
        new_shared
            If True, create a new instance that will replace the previous shared
            instance if it exists.
        """
        if hasattr(cls, "_shared_instance") and not new_shared:
            return cls._shared_instance
        inst = cls(*args, **kwargs)
        cls._shared_instance = inst
        return inst

    @classmethod
    def register_orphan(
        cls, auto_retrieve: bool = True
    ) -> Callable[[type[S]], type[S]]:
        """Return a decorator to register a section as orphaned.

        Parameters
        ----------
        auto_retrieve:
            If True (default), the application class will be registered in the section
            object, which will use it to recover its parametrs from the application
            global instance.
        """

        def func(section: type[S]) -> type[S]:
            if auto_retrieve:
                section._application_cls = cls
            cls._orphaned_sections[section.__name__] = section
            return section

        return func

    def get_orphan_conf(self, section: Section | str) -> dict[str, t.Any]:
        """Return flat dictionnary of keys from section."""
        if isinstance(section, Section):
            section = type(section).__name__

        if section not in self._orphaned_sections:
            raise KeyError(f"{type(self).__name__} has no orphaned section {section}")

        out = {}
        for fullkey, v in self.conf.items():
            first, *key = fullkey.split(".")
            if first == section:
                out[".".join(key)] = v

        return out

    def _get_lines(self, header: str = "") -> list[str]:
        lines = super()._get_lines(header)

        for name, section in self._orphaned_sections.items():
            prefix = f"{name}."
            subconf = {
                k.removeprefix(prefix): v
                for k, v in self.conf.items()
                if k.startswith(prefix)
            }
            if not subconf:
                continue
            traits = section.traits_recursive(config=True, flatten=True)

            # TODO: maybe do it nested
            lines += [header, name]
            for i, (key, value) in enumerate(subconf.items()):
                is_last = i == len(self.conf) - 1
                lines.append(section._get_line_trait(key, traits[key], is_last, value))
        return lines

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
        self._init_direct_traits(self.conf)

        if instanciate is None:
            instanciate = self.auto_instanciate
        if instanciate:
            self._init_subsections(self.conf)

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

        TODO: update
        Currently return None, which can be passed down to the parser
        :class:`argparse.ArgumentParser`.
        To handle more complex cases, like separating arguments for different
        applications (with ``--`` typically), more logic can be setup here.
        """
        exe, *argv = sys.argv
        if path.splitext(path.basename(exe))[0] in ["ipython", "ipykernel_launcher"]:
            if "--" in argv:
                idx = argv.index("--")
                argv = argv[idx + 1 :]
            else:
                return []
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

        is_orphan = first in self._orphaned_sections
        section = self._orphaned_sections.get(first, self)

        out = cv.copy()
        if is_orphan:
            out.key = ".".join(out.path[1:])

        # If an error happens in resolve_key, we have a fallback
        fullkey = out.key
        with ConfigErrorHandler(self, cv.key):
            fullkey, container_cls, trait = section.resolve_key(out.key)
            out.container_cls = container_cls
            out.trait = trait

        if is_orphan:
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
            for key, default in self.defaults_recursive(
                config=True, flatten=True
            ).items():
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

    def __del__(self) -> None:
        delattr(self.__class__, "_instance")
