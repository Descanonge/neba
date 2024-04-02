"""Main entry point for configuration."""

from __future__ import annotations

import itertools
import logging
import sys
import typing as t
from collections import abc
from contextlib import suppress
from logging.config import dictConfig
from os import path

from traitlets import Bool, Dict, Enum, List, Unicode, Union, default, observe
from traitlets.config.configurable import LoggerType, LoggingConfigurable
from traitlets.utils.bunch import Bunch
from traitlets.utils.nested_update import nested_update

from .loader import CLILoader, PyLoader, TomlkitLoader, YamlLoader, to_nested_dict
from .scheme import Scheme
from .util import ConfigErrorHandler

if t.TYPE_CHECKING:
    from .loader import ConfigValue, FileLoader

log = logging.getLogger(__name__)

IS_PYTHONW = sys.executable and sys.executable.endswith("pythonw.exe")


class LoggingMixin(LoggingConfigurable):
    """Add logging functionnalities to an Application.

    This is lifted from :class:`traitlets.config.Application`, with some minor changes.
    """

    _log_formatter_cls: type[logging.Formatter] = logging.Formatter

    log_level = Enum(
        [0, 10, 20, 30, 40, 50, "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        default_value="INFO",
        help="Set the log level by value or name, for the application logger.",
    ).tag(config=True)

    lib_log_level = Enum(
        [0, 10, 20, 30, 40, 50, "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        default_value="WARN",
        help="Set the log level for this library loggers.",
    ).tag(config=True)

    log_datefmt = Unicode(
        "%Y-%m-%d %H:%M:%S",
        help="The date format used by logging formatters for %(asctime)s",
    ).tag(config=True)

    log_format = Unicode(
        "%(levelname)s:%(name)s:%(lineno)d:%(message)s",
        help="The Logging format template",
    ).tag(config=True)

    logging_config = Dict(
        help="""\
        Configure additional log handlers.

        The default stderr logs handler is configured by the log_level, log_datefmt and
        log_format settings.

        This configuration can be used to configure additional handlers (e.g. to output
        the log to a file) or for finer control over the default handlers.

        If provided this should be a logging configuration dictionary, for more
        information see:
        `<https://docs.python.org/3/library/logging.config.html#logging-config-dictschema>`__

        This dictionary is merged with the base logging configuration which defines the
        following:

        * A logging formatter intended for interactive use called ``console``.
        * A logging handler that writes to stderr called ``console`` which uses the
          formatter ``console``.
        * A logger with the name of this application set to :attr:`log_level`.
        * A logger for the ``data_assistant`` library set to :attr: `lib_log_level`.

        This example adds a new handler that writes to a file:

        .. code-block:: python

            c.Application.logging_config = {
                "handlers": {
                    "file": {
                        "class": "logging.FileHandler",
                        "level": "DEBUG",
                        "filename": "<path/to/file>",
                    }
                },
                "loggers": {
                    "<application-name>": {
                        "level": "DEBUG",
                        # NOTE: if you don't list the default "console"
                        # handler here then it will be disabled
                        "handlers": ["console", "file"],
                    },
                },
            }

    """,
    ).tag(config=True)

    def get_default_logging_config(self) -> dict[str, t.Any]:
        """Return the base logging configuration.

        The default is to log to stderr using a StreamHandler, if no default
        handler already exists.

        The log handler level starts at logging.WARN, but this can be adjusted
        by setting the ``log_level`` attribute.

        The ``logging_config`` trait is merged into this allowing for finer
        control of logging.

        """
        config: dict[str, t.Any] = {
            "version": 1,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "level": "DEBUG",
                    "stream": "ext://sys.stderr",
                },
            },
            "formatters": {
                "console": {
                    "class": (
                        f"{self._log_formatter_cls.__module__}"
                        f".{self._log_formatter_cls.__name__}"
                    ),
                    "format": self.log_format,
                    "datefmt": self.log_datefmt,
                },
            },
            "loggers": {
                self.__class__.__name__: {
                    "level": logging.getLevelName(self.log_level),  # type:ignore[arg-type]
                    "handlers": ["console"],
                },
                "data_assistant": {
                    "level": logging.getLevelName(self.lib_log_level),  # type:ignore[arg-type]
                    "handlers": ["console"],
                },
            },
            "disable_existing_loggers": False,
        }

        if IS_PYTHONW:
            # disable logging
            # (this should really go to a file, but file-logging is only
            # hooked up in parallel applications)
            del config["handlers"]
            del config["loggers"]

        return config

    # Simplify default logger, just give Application class name
    @default("log")
    def _log_default(self) -> LoggerType:
        return logging.getLogger(self.__class__.__name__)

    @observe(
        "log_datefmt", "log_format", "log_level", "lib_log_level", "logging_config"
    )
    def _observe_logging_change(self, change: Bunch) -> None:
        # convert log level strings to ints
        log_level = self.log_level
        if isinstance(log_level, str):
            self.log_level = t.cast(int, getattr(logging, log_level))
        lib_log_level = self.lib_log_level
        if isinstance(lib_log_level, str):
            self.lib_log_level = t.cast(int, getattr(logging, lib_log_level))
        self._configure_logging()

    @observe("log", type="default")
    def _observe_logging_default(self, change: Bunch) -> None:
        self._configure_logging()

    def _configure_logging(self) -> None:
        config = self.get_default_logging_config()
        nested_update(config, self.logging_config or {})
        dictConfig(config)
        # make a note that we have configured logging
        self._logging_configured = True

    def __del__(self) -> None:
        self.close_handlers()

    def close_handlers(self) -> None:
        """Close handlers if they have been opened.

        ie if :attr:`_logging_configured` is True.
        """
        if getattr(self, "_logging_configured", False):
            # don't attempt to close handlers unless they have been opened
            # (note accessing self.log.handlers will create handlers if they
            # have not yet been initialised)
            lib_logger = logging.getLogger("data_assistant")
            for handler in itertools.chain(self.log.handlers, lib_logger.handlers):
                with suppress(Exception):
                    handler.close()
            self._logging_configured = False


class ApplicationBase(Scheme, LoggingMixin):
    """Base application class.

    Orchestrate the loading of configuration keys from files or from command line
    arguments.
    Pass the combined configuration keys to the appropriate schemes in the configuration
    tree structure. This validate the values and instanciate the configuration objects.
    """

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
        default_value=["config.toml", "config.py"],
        help=(
            "Path to configuration files. Either relative from interpreter "
            "working directory or absolute."
        ),
    )

    auto_instanciate = Bool(
        True,
        help=(
            """
            Instanciate all schemes in the configuration tree at application start.

            Instanciation is necessary to fully validate the values of the configuration
            parameters, but in case systematic instanciation is unwanted this can be
            disabled (for example in case of costly instanciations)."""
        ),
    )

    ignore_cli = Bool(False, help="If True, do not parse command line arguments.")

    file_loaders: list[type[FileLoader]] = [TomlkitLoader, YamlLoader, PyLoader]
    """List of possible configuration loaders from file, for different formats.

    Each will be tried until an appropriate loader is found. Currently, loaders only
    look at the extension.
    """

    def __init__(self, *args, **kwargs) -> None:
        self.cli_conf: dict[str, ConfigValue] = {}
        """Configuration values obtained from command line arguments."""
        self.file_conf: dict[str, ConfigValue] = {}
        """Configuration values obtained from configuration files."""

        self._extra_parameters_args: list[tuple[list, dict[str, t.Any]]] = []
        """Extra parameters passed to the command line parser."""
        self.extra_parameters: dict[str, t.Any] = {}
        """Extra paramaters retrieved by the command line parser."""

    def start(
        self,
        argv: list[str] | None = None,
        ignore_cli: bool | None = None,
        instanciate: bool | None = None,
    ) -> None:
        """Initialize and start application.

        - Parse command line arguments (optional)
        - Load configuration file(s).
        - Merge configurations
        - Instanciate schemes objects (optional)

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
            If True, instanciate all schemes. If not None, this argument overrides
            :attr:`auto_instanciate`.
        """
        # Parse CLI first
        #  -> needed for help, or setting config filenames
        # This sets self.cli_conf
        if ignore_cli is None:
            ignore_cli = self.ignore_cli
        if not ignore_cli:
            self.parse_command_line(argv)
            log.debug("Found config keys from CLI: %s", ", ".join(self.cli_conf.keys()))

        # Read config files
        # This sets self.file_conf
        if self.config_files:
            self.load_config_files()

        self.conf = self.merge_configs(self.file_conf, self.cli_conf)

        if instanciate is None:
            instanciate = self.auto_instanciate
        if instanciate:
            self.instanciate_subschemes(to_nested_dict(self.conf))

    def _create_cli_loader(
        self, argv: list[str] | None, log: logging.Logger | None = None, **kwargs
    ) -> CLILoader:
        """Create a CLILoader instance to parse command line arguments."""
        return CLILoader(self, **kwargs)

    def parse_command_line(
        self, argv: list[str] | None = None, log: logging.Logger | None = None, **kwargs
    ):
        """Parse command line arguments and populate :attr:`cli_conf`.

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
        self.cli_conf = loader.get_config()

    def get_argv(self) -> list[str] | None:
        """Return command line arguments.

        Currently return None, which can be passed down to the parser
        :class:`argparse.ArgumentParser`.
        To handle more complex cases, like separating arguments for different
        applications (with ``--`` typically), more logic can be setup here.
        """
        return None

    def load_config_files(self) -> None:
        """Load configuration values from files and populate :attr:`config_files`."""
        if isinstance(self.config_files, str):
            self.config_files = [self.config_files]

        if not self.config_files:
            return

        file_confs: dict[str, dict[str, ConfigValue]] = {}
        for filepath in self.config_files:
            if not path.isfile(filepath):
                continue

            loader_cls = self._select_file_loader(filepath)
            loader = loader_cls(filepath, self)
            file_confs[filepath] = loader.get_config()

        if len(file_confs) == 0:
            log.info("No config files found (%s)", str(self.config_files))
        elif len(file_confs) == 1:
            self.file_conf = list(file_confs.values())[0]
        else:
            self.file_conf = self.merge_configs(*file_confs.values())

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

    def resolve_config(
        self, config: abc.Mapping[str, ConfigValue]
    ) -> dict[str, ConfigValue]:
        """Resolve all keys in the config and validate it.

        Keys can use aliases/shortcuts, and also be under the form of "class keys"
        ``SchemeClassName.trait_name = ...``. We normalize all keys as dot separated
        attributes names, without shortcuts, that point a trait.
        Keys that do not resolve to any known trait will raise error.

        Values specified with class keys will be duplicated over all places where the
        scheme class has been used. Their priority will automatically be set lower.

        The trait and containing scheme class will be added to each :class:`ConfigValue`.

        Parameters
        ----------
        config
            Flat mapping of all keys to their ConfigValue

        Returns
        -------
        resolved_config
            Flat mapping of normalized keys to their ConfigValue
        """
        config_classes = [cls.__name__ for cls in self._classes_inc_parents()]

        # Transform Class.trait keys into fullkeys
        no_class_key: dict[str, ConfigValue] = {}
        for key, val in config.items():
            # Set the priority of class traits lower and duplicate them
            # for each instance of their class in the config tree
            if key.split(".")[0] in config_classes:
                val.priority = 10
                # we assume we will have at least one fullkey, since the classname
                # appeared in cls._classes_inc_parents
                for fullkey in self.resolve_class_key(key):
                    no_class_key[fullkey] = val.copy(key=fullkey)
            else:
                no_class_key[key] = val

        # Resolve fullpath for all keys
        output = {}
        for key, val in no_class_key.items():
            # If an error happens in class_resolve_key, we have a fallback
            fullkey = key
            with ConfigErrorHandler(self, key):
                fullkey, container_cls, trait = self.class_resolve_key(key)
                val.container_cls = container_cls
                val.trait = trait
            output[fullkey] = val

        return output

    def add_extra_parameter(self, *args, **kwargs):
        """Add a configurable trait to this application configuration.

        Parameters
        ----------
        args, kwargs
            Passed to :meth:`argparse.ArgumentParser.add_argument`.
        """
        self._extra_parameters_args.append((args, kwargs))

    def write_config(
        self,
        filename: str | None = None,
        comment: str = "full",
        overwrite: bool | None = None,
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

            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        overwrite:
            If the target file already exists: if None (default) ask whether to
            overwrite, if a boolean either overwrite (True) the existing file, or not
            (False).
        """
        if filename is None:
            if isinstance(self.config_files, list | tuple):
                filename = self.config_files[0]
            else:
                filename = self.config_files

        filename = path.realpath(filename)

        if path.exists(filename) and overwrite is None:
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
            overwrite = not answer.startswith("n")
            if not overwrite:
                return

            log.info("Overwriting configuration file %s.", filename)

        loader = self._select_file_loader(filename)(filename, self)
        lines = loader.to_lines(comment=comment)

        with open(filename, "w") as f:
            f.write("\n".join(lines))

    def exit(self, exit_status: int | str = 0):
        """Exit python interpreter."""
        sys.exit(exit_status)
