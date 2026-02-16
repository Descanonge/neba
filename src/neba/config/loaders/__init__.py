"""Configuration loaders.

Similarly to traitlets, the :class:`Application<.Application>` object delegates the work
of loading configuration values from various sources (config files, CLI, etc.).

Because we want to allow nested configurations, the traitlets loaders are not really
appropriate and difficult to adapt. Therefore we start from scratch (but still borrowing
some code...).

The application will try to make sense of the configuration it receives from the loader.
It should raise on any malformed or invalid config key, but the loader can still act
upstream, for instance on duplicate keys.

"""

from .cli import CLILoader
from .core import ConfigLoader, ConfigValue, DictLoader, FileLoader, Undefined

__all__ = [
    "CLILoader",
    "ConfigLoader",
    "ConfigValue",
    "DictLoader",
    "FileLoader",
    "Undefined",
]
