"""Main entry point for configuration."""

from __future__ import annotations

import logging
import sys
import typing as t
from collections.abc import Mapping
from os import path

from traitlets import (
    Bunch,
    Enum,
    Int,
    List,
    TraitType,
    Unicode,
    Union,
    default,
    observe,
)
from traitlets.config.configurable import LoggingConfigurable

from data_assistant.util import get_classname, import_item

from .loaders import CLILoader, ConfigValue
from .section import Section
from .util import ConfigError, UnknownConfigKeyError, did_you_mean

if t.TYPE_CHECKING:
    from .loaders import ConfigValue, FileLoader

log = logging.getLogger(__name__)

S = t.TypeVar("S", bound=Section)


class ApplicationBase(Section, LoggingConfigurable):
    """Base application class.

    Orchestrate the loading of configuration keys from files or from command line
    arguments.
    Pass the combined configuration keys to the appropriate sections in the configuration
    tree structure. This validate the values and instantiate the configuration objects.
    """

    file_loaders: dict[tuple[str, ...], str | type] = {
        ("toml",): "data_assistant.config.loaders.toml.TomlkitLoader",
        ("py", "ipy"): "data_assistant.config.loaders.python.PyLoader",
        ("yaml", "yml"): "data_assistant.config.loaders.yaml.YamlLoader",
        ("json",): "data_assistant.config.loaders.json.JsonLoader",
    }
    """Mapping from file extension to loader class or location of loader to import."""

    auto_instantiate = True
    """Instantiate all sections in the configuration tree at application start.

    Instantiation is necessary to fully validate the values of the configuration
    parameters, but in case systematic instantiation is unwanted this can be disabled
    (for example in case of costly instantiations).
    """

    ignore_cli = False
    """If True, do not parse command line arguments."""

    # -- Config --

    config_files = Union(
        [Unicode(), List(Unicode())],
        default_value=["config.toml"],
        help=(
            "Path to configuration files. Either relative from interpreter "
            "working directory or absolute."
        ),
    )

    # -- Log config --

    log_level = Union(
        [Enum(("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")), Int()],
        default_value="INFO",
        help="Set the log level by value or name.",
    )

    log_datefmt = Unicode(
        "%Y-%m-%d %H:%M:%S",
        help="The date format used by logging formatters for 'asctime'",
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
                get_classname(self): {
                    "level": logging.getLevelName(self.log_level)
                    if isinstance(self.log_level, str)
                    else self.log_level,
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
        return logging.getLogger(get_classname(self))

    # -- Instance attributes --

    conf: dict[str, ConfigValue]
    """Configuration values obtained from command line arguments and configuration
    files."""
    cli_conf: dict[str, ConfigValue]
    """Configuration values obtained from command line arguments."""
    file_conf: dict[str, ConfigValue]
    """Configuration values obtained from configuration files."""

    def __init__(self, /, start: bool = True, **kwargs) -> None:
        super().__init__(init_subsections=False)

        self.conf = {}
        self.cli_conf = {}
        self.file_conf = {}

        if start:
            self.start(**kwargs)

    def start(
        self,
        argv: list[str] | None = None,
        ignore_cli: bool | None = None,
        instantiate: bool | None = None,
    ) -> None:
        """Initialize and start application.

        - Parse command line arguments (optional)
        - Load configuration file(s)
        - Merge configurations
        - (Re)Apply configuration to Application
        - Instantiate sections objects (optional)

        Instantiation is necessary to fully validate the values of the configuration
        parameters, but in case systematic instantiation is unwanted this can be
        disabled (for example in case of costly instantiations).

        Parameters
        ----------
        argv
            Override command line arguments to parse. If left to None, arguments are
            obtained from :meth:`get_argv`.
        ignore_cli
            If True, do not parse command line arguments. If not None, this argument
            overrides :attr:`ignore_cli`.
        instantiate
            If True, instantiate all sections. If not None, this argument overrides
            :attr:`auto_instantiate`.
        """
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

        # make a copy
        conf = dict(self.conf)

        # Apply config relevant to this instance (only self, not recursive)
        self._init_direct_traits(conf)

        if instantiate is None:
            instantiate = self.auto_instantiate
        if instantiate:
            self._init_subsections(conf)
            if conf:
                raise KeyError(
                    f"Extra parameters for {self.__class__.__name__} {list(conf.keys())}"
                )

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
        return loader.get_config(argv)

    def get_argv(self) -> list[str] | None:
        """Return command line arguments.

        Try to detect if launched from ipython or ipykernel (jupyter), in which case
        strip parameters before the first '--' are stripped.
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
    def add_extra_parameters(
        cls, traits: Mapping[str, TraitType] | None = None, **kwargs: TraitType
    ):
        """Add extra parameters to a section named 'extra'.

        The section will be created if it does not exist already.

        Parameters
        ----------
        traits, kwargs
            Parameters to add as traits.
        """
        if traits is None:
            traits = {}
        traits = dict(traits)
        traits.update(**kwargs)

        current_extra_cls = cls._subsections.get("extra", Section)
        extra_cls: type[Section] = type("ExtraSection", (current_extra_cls,), traits)
        cls._subsections["extra"] = extra_cls

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
        ext = path.splitext(filename)[1]
        for loader_exts, loader in self.file_loaders.items():
            if ext.lstrip(".") in loader_exts:
                if isinstance(loader, str):
                    log.debug("Importing loader %s", loader)
                    loader_cls = import_item(loader)
                else:
                    loader_cls = loader
                select = loader_cls
                break
        if select is None:
            raise KeyError(
                f"Did not find appropriate loader for config file {filename}. "
                f" Supported formats are {self.file_loaders}"
            )
        return select

    def resolve_config_value(self, cv: ConfigValue) -> ConfigValue:
        """Validate a ConfigValue.

        Keys can use aliases/shortcuts. We normalize all keys as dot separated
        attributes names, without shortcuts, that point a trait. Keys that do not
        resolve to any known trait will raise error.

        The trait and containing section class will be added to the
        :class:`ConfigValue`.
        """
        section: type[Section] = type(self)
        out = cv.copy()

        try:
            fullkey, container_cls, trait = section.resolve_key(out.key)
            out.container_cls = container_cls
            out.trait = trait
            out.key = fullkey
        except ConfigError as e:
            if isinstance(e, UnknownConfigKeyError):
                suggestion = did_you_mean(self.keys(aliases=True), cv.key)
                if suggestion is not None:
                    e.add_note(f"Did you mean '{suggestion}'?")
            e.add_note(f"Error in configuration key '{cv.key}' from {cv.origin}.")
            raise e

        return out

    def copy(self, **kwargs) -> t.Self:
        """Return a copy."""
        out = self.__class__(start=False, **kwargs)
        out.conf = self.conf.copy()
        out.cli_conf = self.cli_conf.copy()
        out.file_conf = self.file_conf.copy()
        config = self.as_dict()
        Section.__init__(out, config, **kwargs)
        return out

    def write_config(
        self,
        filename: str | None = None,
        comment: str = "full",
        use_current_values: bool = True,
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
        use_current_values:
            If True (default), use the current values of the traits instead, otherwise
            use the trait default value.
        clobber:
            If the target file already exists, either:

            * abort: do nothing
            * overwrite: the file is completely overwritten with the current
              configuration
            * update: the configuration keys specified in the existing file are kept.
              They take precedence over the current application config.
            * None: ask what to do interactively in the console
        """
        options = dict(u="update", o="overwrite", a="abort")
        default = "a"
        inits = [i.upper() if i == default else i for i in options.keys()]

        # config to write, start with non-default traits
        config: dict[str, ConfigValue] = {}
        if use_current_values:
            for key, default in self.defaults_recursive(config=True).items():
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

        with open(filename, "w") as fp:
            loader.write(fp, comment=comment)

    def exit(self, exit_status: int | str = 0):
        """Exit python interpreter."""
        sys.exit(exit_status)
