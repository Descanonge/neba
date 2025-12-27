"""Configuration loaders.

Similarly to traitlets, the
:class:`Application<data_assistant.config.application.ApplicationBase>` object delegates
the work of loading configuration values from various sources (config files, CLI, etc.).

Because we want to allow nested configurations, the traitlets loaders are not really
appropriate and difficult to adapt. Therefore we start from scratch (but still borrowing
some code...).

The application will try to make sense of the configuration it receives from the loader.
It should raise on any malformed or invalid config key, but the loader can still act
upstream, for instance on duplicate keys.

Presently, the application accepts different
types of keys:

* "fullpaths": they define the succession of attribute names leading to a specific
  trait (example ``group.subgroup.sub_subgroup.trait_name``)
* "fullpaths with shortcuts": :class:`sections<data_assistant.config.section.Section>` can
  define shortcuts to avoid repeating parts of the fullpath (for example we could have a
  key ``shortcut.trait_name`` that would be equivalent to the one above).
* "class keys": they use the :class:`~.config.section.Section` class name followed by that
  of a trait (for example ``SectionClassName.trait_name``). Since we allow a section to be
  re-used multiple times in the nested configuration, this can be equivalent to
  specifying multiple parameters with the same values. They will have a lower priority
  than specifying the full path.
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
