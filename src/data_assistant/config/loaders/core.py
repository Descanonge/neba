"""Configuration loaders bases."""

from __future__ import annotations

import logging
import typing as t
from collections import abc
from copy import deepcopy
from os import path

from traitlets.traitlets import Container, HasTraits, TraitError, TraitType, Union
from traitlets.utils.sentinel import Sentinel

from ..util import (
    ConfigError,
    ConfigParsingError,
    MultipleConfigKeyError,
    flatten_dict,
    nest_dict,
)

if t.TYPE_CHECKING:
    from .application import ApplicationBase
    from .scheme import Scheme

Undefined = Sentinel(
    "Undefined", "data-assistant", "Configuration value not (yet) set or parsed."
)
""":class:`traitlets.Sentinel<traitlets.utils.sentinel.Sentinel>` object for undefined configuration values.

Allows to separate them from simply ``None``.
"""  # noqa: E501


class ConfigValue:
    """Value obtained from a source.

    It stores a number of information about the value (its origin, initial value, etc.).

    Parameters
    ----------
    input
        The initial value obtained from a configuration source.
    key
        The key it was associated with in the source. For information purpose mainly.
    origin
        A string specifying the configuration source it was found in. For information
        purpose mainly.
    """

    def __init__(self, input: t.Any, key: str, origin: str | None = None):
        if isinstance(input, list):
            if len(input) == 1:
                input = input[0]

        self.key = key
        """The key this value was associated to."""
        self.input = input
        """The initial value obtained."""
        self.origin = origin
        """A description of the configuration source it was found in."""

        self.value: t.Any = Undefined
        """The parameter value once parsed.

        By default, it equals to :attr:`Undefined`.
        """
        self.trait: TraitType | None = None
        """The trait instance specifying the parameter to configure."""
        self.container_cls: type[HasTraits] | None = None
        """The configurable class that owns the trait."""
        self.priority: int = 100
        """Priority of the value used when merging config.

        If two values, possibly from different sources, target the same parameter the
        value with the highest priority is used.
        """

    def __str__(self) -> str:
        s = [str(self.get_value())]
        if self.origin is not None:
            s.append(f"({self.origin})")
        return " ".join(s)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"

    def copy(self) -> t.Self:
        """Return a copy of this instance."""
        return deepcopy(self)

    def get_value(self) -> t.Any:
        """Return the actual value to use as parameter.

        By default, use the :attr:`value` attribute, unless it is :attr:`Undefined` then
        use the initial value (possibly unparsed).
        """
        if self.value is not Undefined:
            return self.value
        return self.input

    def parse(self) -> None:
        """Parse the initial value.

        Parsing traits is done by either
        :meth:`TraitType.from_string<traitlets.TraitType.from_string>` or
        :meth:`Container.from_string_list<traitlets.Container.from_string_list>` for
        container traits.

        We have to choose the correct function, and :class:`traitlets.Union` traits does
        not do that (if no correct parsing is found it just return the input string, and
        if a correct value is extracted the trait tries to validate it and may fail and
        raise).

        This method tries to handles containers and union more gracefully. If all
        options have been tried and no parsing was successful the function will
        raise.
        """
        if self.trait is None:
            raise ConfigParsingError(
                f"Cannot parse key '{self.key}', has no associated trait."
            )

        def _try(attr: str, trait: TraitType, src: str | list[str]) -> bool:
            try:
                self.value = getattr(trait, attr)(src)
                return True
            except (AttributeError, TraitError, ValueError):
                return False

        def try_item(trait: TraitType, src: str) -> bool:
            return _try("from_string", trait, src)

        def try_list(trait: Container, src: list[str]) -> bool:
            return _try("from_string_list", trait, src)

        def _parse(trait: TraitType, src: str | list[str]) -> bool:
            src = [src] if isinstance(src, str) else src

            # Handle lists
            if isinstance(trait, Container) and try_list(trait, src):
                return True

            # Handle Union with lists
            if isinstance(trait, Union):
                for trait_type in trait.trait_types:
                    if _parse(trait_type, src):
                        return True

            # Handle everything else
            if len(src) == 1 and try_item(trait, src[0]):
                return True

            return False

        if _parse(self.trait, self.input):
            return

        traitname = self.trait.__class__.__name__
        raise ConfigParsingError(
            f"Could not parse '{self.input}' for trait '{self.key}' ({traitname})."
        )


class ConfigLoader:
    """Abstract ConfigLoader.

    Define the public API that will be used by the
    :class:`Application<.application.ApplicationBase>` object, as well as some common
    logic.

    Parameters
    ----------
    app
        Parent application that created this loader.
    log
        Logger instance.
    """

    def __init__(self, app: ApplicationBase, log: logging.Logger | None = None):
        self.app = app
        """Parent application that created this loader.

        It will be used to deal with exceptions, and to resolve/normalize the config
        once loaded.
        """
        if log is None:
            log = logging.getLogger(__name__)
        self.log = log
        self.config: dict[str, ConfigValue] = {}
        """Configuration dictionnary mapping keys to ConfigValues.

        It should be a flat dictionnary.
        """

    def clear(self) -> None:
        """Empty the config."""
        self.config.clear()

    def add(self, key: str, value: ConfigValue):
        """Add key to configuration dictionnary.

        Raises
        ------
        MultipleConfigKeyError
            If the key is already present in the current configuration.
        """
        if key in self.config:
            raise MultipleConfigKeyError(key, [self.config[key], value])
        self.config[key] = value

    def get_config(
        self,
        *args: t.Any,
        apply_application_traits: bool = True,
        resolve: bool = True,
        **kwargs,
    ) -> dict[str, ConfigValue]:
        """Load and return a proper configuration dict.

        This method clears the existing config, call :meth:`load_config` to populate the
        :attr:`config` attribute, apply parameters to the root application,
        resolve/normalize the config and return it.

        Parameters to be applied to the application before proper resolution of the
        whole configuration are detected in a simple manner. Only single level keys and
        class keys corresponding to an existing application trait are used. Aliases not
        yet supported.

        Parameters
        ----------
        args, kwargs
            Passed to :meth:`load_config`.
        """
        self.clear()
        self.load_config(*args, **kwargs)

        if apply_application_traits:
            self.apply_application_traits()

        if resolve:
            self.config = self.app.resolve_config(self.config)

        return self.config

    def apply_application_traits(self) -> None:
        """Apply config for Application."""
        for key, val in self.config.items():
            keypath = key.split(".")
            if (len(keypath) == 1 and key in self.app.trait_names()) or (
                len(keypath) == 2 and keypath[0] == self.app.__class__.__name__
            ):
                traitname = keypath[-1]
                val.trait = self.app.traits()[traitname]
                if val.value is Undefined:
                    val.parse()
                setattr(self.app, traitname, val.get_value())

    def load_config(self, *args, **kwargs) -> None:
        """Populate the config attribute from a source.

        :Not implemented:
        """
        raise NotImplementedError


class FileLoader(ConfigLoader):
    """Load config from a file.

    Common logic goes here.

    Parameters
    ----------
    filename
        Path of configuration file to load.
    """

    extensions: list[str] = []
    """File extensions that are supported by this loader."""

    def __init__(self, app: ApplicationBase, filename: str, *args, **kwargs) -> None:
        super().__init__(app, *args, **kwargs)
        self.filename = filename
        self.full_filename = path.abspath(filename)

    @classmethod
    def can_load(cls, filename: str) -> bool:
        """Return if this loader class is appropriate for this config file.

        This is a classmethod to avoid unnecessary/unwanted library import that might
        happen at initialization.

        By default, only check supported file extensions.
        """
        _, ext = path.splitext(filename)
        return ext.lstrip(".") in cls.extensions

    def to_lines(
        self, comment: t.Any = None, show_existing_keys: bool = False
    ) -> list[str]:
        """Generate lines of a configuration file corresponding to the app config tree.

        If `show_existing_keys` is true, the keys present in the original file are
        loaded into this instance :attr:`config` attribute.

        Parameters
        ----------
        comment
            Include more or less information as comments. Can be one of:

            * full: all information about traits is included
            * no-help: trait help attribute is not included
            * none: no information is included, only the key and default value

            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        show_existing_keys
            If True, do not comment ``key = value`` lines that are present in the
            original file (default is False).
        """
        if show_existing_keys:
            classes = {cls.__name__: cls for cls in self.app._classes_inc_parents()}
            self.get_config(apply_application_traits=False, resolve=False)
            valid = {}
            for key, value in self.config.items():
                keypath = key.split(".")
                if (
                    len(keypath) == 2
                    and keypath[0] in classes
                    and keypath[1] in classes[keypath[0]].class_trait_names(config=True)
                ):
                    for fullkey in self.app.resolve_class_key(keypath):
                        _, scheme, trait = self.app.resolve_key(fullkey)
                        trait._validate(scheme, value.get_value())
                    valid[key] = value
                    continue
                try:
                    fullkey, scheme, trait = self.app.resolve_key(keypath)
                    trait._validate(scheme, value.get_value())
                    valid[key] = value
                except ConfigError:
                    pass
            self.config = valid
        return self._to_lines(comment=comment, show_existing_keys=show_existing_keys)

    def _to_lines(
        self, comment: t.Any = None, show_existing_keys: bool = False
    ) -> list[str]:
        """Generate lines of a configuration file corresponding to the app config tree.

        If `show_existing_keys` is true, the keys present in the original file are
        loaded into this instance :attr:`config` attribute.
        This includes unresolved class-keys. It is advised to pop keys from the
        configuration as the application config-tree is walked. At the end, only
        class keys should be left.

        Parameters
        ----------
        comment
            Include more or less information as comments. Can be one of:

            * full: all information about traits is included
            * no-help: trait help attribute is not included
            * none: no information is included, only the key and default value

            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        show_existing_keys
            If True, do not comment ``key = value`` lines that are present in this
            loader instance :attr:`config` attribute (default is False).
        """
        raise NotImplementedError("Implement for different file formats.")


class DictLikeLoaderMixin(ConfigLoader):
    """Load a configuration from a mapping.

    As there are no way to differentiate between a mapping for a dictionary trait and
    one for a nested scheme, we need to check the existing keys before resolving. We
    only look for existing subschemes and aliases, otherwise we assume this is a
    dict-like value.
    """

    def resolve_mapping(self, input: abc.Mapping, origin: str | None = None):
        """Flatten an input nested mapping."""
        # Some keys might be dot-separated. To make sure we are completely nested:
        input = flatten_dict(input)
        input = nest_dict(input)

        def recurse(d: abc.Mapping, scheme: type[Scheme], key: list[str]):
            for k, v in d.items():
                if k in scheme._subschemes:
                    assert isinstance(v, abc.Mapping)
                    recurse(v, scheme._subschemes[k], key + [k])
                elif k in scheme.aliases:
                    assert isinstance(v, abc.Mapping)
                    # resolve alias
                    sub = scheme
                    alias = scheme.aliases[k].split(".")
                    for al in alias:
                        sub = sub._subschemes[al]
                    recurse(v, sub, key + alias)
                else:
                    fullkey = ".".join(key + [k])
                    value = ConfigValue(v, fullkey, origin=origin)
                    # no parsing, directly to values
                    value.value = value.input
                    self.add(fullkey, value)

        recurse(input, self.app.__class__, [])


class DictLikeLoader(DictLikeLoaderMixin):
    """Loader for mappings."""

    def load_config(self, input: abc.Mapping) -> None:
        """Populate the config attribute from a nested mapping."""
        self.config = self.resolve_mapping(input)
