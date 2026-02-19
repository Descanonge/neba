"""Type definitions."""

from collections.abc import Sequence
from typing import Any


class ConfigError(Exception):
    """General exception for config loading."""


class UnknownConfigKeyError(ConfigError):
    """Key path does not lead to any known trait."""


class ConfigParsingError(ConfigError):
    """Unable to parse a config value."""


class MultipleConfigKeyError(ConfigError):
    """A parameter was specified more than once."""

    def __init__(self, key: str, values: Sequence[Any], msg: str | None = None) -> None:
        super().__init__()

        if msg is None:
            msg = (
                f"Configuration key '{key}' was specified more than once "
                f"with values {values}"
            )

        self.message = msg
        self.key = key
        self.values = values
