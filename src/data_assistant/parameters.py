"""Project-wide parameters management."""

import argparse
import os
from collections.abc import Sequence
from os import path
from typing import Any, Callable

import configargparse  # type: ignore

PathLike = str | os.PathLike


class ParametersManager:
    """Retrieve parameters from command line and config files.

    Allows to automatically construct an :class:`configargparse.ArgumentParser`
    from a list of previously registered arguments (or parameters).
    Useful for project-wide definition of parameters that are not necessarily
    used by all scripts. Each script can retrieve a subset of parameters.

    .. note::

        This class uses :class:`configargparse.ArgumentParser` but this is
        interchangeable with built-in :class:`argparse.ArgumentParser`.
        Only :func:`new_parser` needs to be overriden to change the parser class.
    """

    def __init__(self, config_files: Sequence[str],
                 sections: str | Sequence[str] = 'parameters'):
        self.config_files: Sequence[str] = config_files

        if isinstance(sections, str):
            sections = [sections]
        self.sections: Sequence[str] = sections

        self.parameters_args: dict[str, tuple[tuple[Any, ...], dict]] = {}
        self._actions: dict[str, argparse.Action] = {}
        self._actions_group: dict[str, str | None] = {}
        self.groups_descr: dict[str, str | None] = {}
        self._active_group: str | None = None
        self.parser = self.new_parser()

    def register(self, *args, **kwargs):
        self.register_parameter(*args, **kwargs)

    def register_parameter(self, *args, group: str | None = None, **kwargs):
        """Register a new parameter definition.

        Arguments are passed to this instance argument parser (by default
        :class:`configargparse.ArgumentParser`).
        See :func:`argparse.ArgumentParser.add_argument` for details on this
        functions arguments.

        The arguments are stored to recreate a parser with only some selected
        arguments later.
        """
        if group is None and self._active_group is not None:
            group = self._active_group
        if group is not None and group not in self.groups_descr:
            raise KeyError(f"Unknown group '{group}.")
        action = self.parser.add_argument(*args, **kwargs)
        self._actions_group[action.dest] = group
        self.parameters_args[action.dest] = (args, kwargs)
        self._actions[action.dest] = action

    def add_group(self, name: str, description: str | None = None):
        self.groups_descr[name] = description

    def set_active_group(self, group: str | None):
        if group is not None and group not in self.groups_descr:
            raise KeyError(f"Unknown group '{group}.")
        self._active_group = group

    def new_parser(self) -> argparse.ArgumentParser:
        """Return an instance of argument parser."""
        parser = configargparse.ArgParser(
            default_config_files=self.config_files,
            config_file_parser_class=configargparse.IniConfigParser(
                self.sections, split_ml_text_to_list=False
            )
        )
        return parser

    def get_parser(
            self,
            select_params: Sequence[str] | None
    ) -> argparse.ArgumentParser:
        """Create a new parser for only some parameters.

        Parameters
        ----------
        select_params:
            Paremeters to parse for. If None, all registered parameters are
            selected.
        """
        if select_params is None:
            select_params = list(self.parameters_args.keys())

        parser = self.new_parser()
        groups = {}

        for param in select_params:
            parser_or_group: argparse.ArgumentParser | argparse._ArgumentGroup
            parser_or_group = parser
            if (group_name := self._actions_group[param]) is not None:
                if group_name not in groups:
                    groups[group_name] = parser.add_argument_group(
                        group_name, description=self.groups_descr[group_name])
                parser_or_group = groups[group_name]
            param_args, param_kwargs = self.parameters_args[param]
            parser_or_group.add_argument(*param_args, **param_kwargs)

        return parser

    def get_parameters(
            self,
            select_params: Sequence[str] | None = None,
            add_params: Callable[[argparse.ArgumentParser], None] | None = None,
            ignore_unknown_args: bool = False,
            ignore_command_line_args: bool = False) -> dict:
        """Get parameters from command line and config files.

        Parameters
        ----------
        select_params:
            Paremeters to parse for. If None, all registered parameters are
            selected.
        add_params:
            Function acting on the current parser that will be called after
            creating the parser. Can be used to add un-registered parameters.
        ignore_unknown_args:
            If True, will ignore unknown arguments. If False (default), an
            error will be raised if the command line contains unknown arguments.
        ignore_command_line_args:
            If True, will ignore command line arguments completely. Default
            is False.
        """
        self.last_parser = self.get_parser(select_params)

        # Callback
        if add_params is not None:
            add_params(self.last_parser)

        args: Sequence[str] | None = None
        if ignore_command_line_args:
            args = []

        params, _ = self.last_parser.parse_known_args(args)

        # Just to check if we have some unwanted arguments
        # We need to use the full parser because `last_parser` does not know
        # about all the parameters that can be present in config files
        if not ignore_unknown_args:
            self.parser.parse_args(args)

        return vars(params)

    def write_default_config(
            self,
            filename: PathLike
    ):
        """Write default values to a config file."""
        import textwrap
        if path.isfile(filename):
            raise ValueError(f"'{filename}' already exists.")

        with open(filename, 'w') as f:
            print('[parameters]', file=f)

            for action in self._actions.values():
                # check if at least one of the option string is --long-form
                if not any(arg.startswith(2*c)
                           for arg in action.option_strings
                           for c in self.parser.prefix_chars):
                    continue

                print(f'\n# {action.option_strings}', file=f)
                if action.help:
                    for line in textwrap.wrap(action.help):
                        print('# ' + line, file=f)
                print(f'{action.dest} = {action.default}', file=f)


params_manager = ParametersManager(['./parameters.ini'])

params_manager.register_parameter(
    '-r', '--region', type=str, default='GS',
    help='Name of the region to work in.'
)
params_manager.register_parameter(
    '-d', '--data', type=str, default='modis',
    help='Type of data to work on.'
)
params_manager.register_parameter(
    '--scale', action=argparse.BooleanOptionalAction, default=False,
    help='Size of the HI window in km.'
)

params = params_manager.get_parameters(['region'])
