"""Type definitions."""

import typing as t
from collections import abc


class ConfigError(Exception):
    """General exception for config loading."""


class UnknownConfigKeyError(ConfigError):
    """Key path does not lead to any known trait."""


class ConfigParsingError(ConfigError):
    """Unable to parse a config value."""


class MultipleConfigKeyError(ConfigError):
    """A parameter was specified more than once."""

    def __init__(
        self, key: str, values: abc.Sequence[t.Any], msg: str | None = None
    ) -> None:
        super().__init__()

        if msg is None:
            msg = (
                f"Configuration key '{key}' was specified more than once "
                f"with values {values}"
            )

        self.message = msg
        self.key = key
        self.values = values
