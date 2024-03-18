"""Main entry point for configuration."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from os import path
from typing import TYPE_CHECKING

from traitlets import Bool, Instance, List, Unicode, Union

from .loader import CLILoader, PyLoader, TomlkitLoader, YamlLoader, to_nested_dict
from .scheme import Scheme

if TYPE_CHECKING:
    from traitlets.config.configurable import Configurable
    from traitlets.traitlets import TraitType

    from .loader import ConfigLoader, ConfigValue, FileLoader


class ApplicationBase(Scheme):
    """Base application class.

    Orchestrate the loading of configuration keys from files or from command line
    arguments.
    Pass the combined configuration keys to the appropriate schemes in the configuration
    tree structure. This validate the values and instanciate the configuration objects.
    """

    strict_parsing = Bool(
        True,
        help=(
            """If true, raise errors when encountering unknown arguments or
            configuration keys. Else only prints a warning."""
        ),
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
        self.file_conf: dict[str, ConfigValue] = {}

        self.log = logging.getLogger(__name__)

        self.start()

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

        self.apply_cli_config()

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
        for key, val in self.cli_conf.items():
            if val.container_cls is not None and isinstance(self, val.container_cls):
                setattr(self, key.split(".")[-1], val.value)

    def load_config_files(self, log: logging.Logger | None = None):
        if log is None:
            log = self.log
        if isinstance(self.config_files, str):
            self.config_files = [self.config_files]

        file_confs: dict[str, dict[str, ConfigValue]] = {}
        for filepath in self.config_files:
            if not path.isfile(filepath):
                continue

            loader_cls = self._select_file_loader(filepath)
            loader = loader_cls(filepath, self, log=log)
            file_confs[filepath] = loader.get_config()

        if len(file_confs) > 1:
            self.file_conf = self.merge_configs(*file_confs.values())
        else:
            self.file_conf = list(file_confs.values())[0]

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

    def add_extra_parameter(
        self,
        key: str,
        trait: TraitType,
    ):
        """Add a configurable trait to this application configuration.

        Parameters
        ----------
        key:
            Path specifying the place and name of the trait to add to the configuration
            tree.
        trait:
            Trait object to add. It will automatically be tagged as configurable.
        """
        raise NotImplementedError()
        # trait.tag(config=True)
        # setattr(dest, name, trait)
        # dest.setup_class(dest.__dict__)  # type: ignore

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
            Write to this file. If None, the first filename from :attr:`config_files` is
            used.
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

        loader = self._select_file_loader(filename)(filename, self, self.log)
        lines = loader.to_lines(comment=comment)

        # Remove trailing whitespace
        lines = [line.rstrip() for line in lines]

        with open(filename, "w") as f:
            f.write("\n".join(lines))

    def exit(self, exit_status: int | str = 0):
        sys.exit(exit_status)
