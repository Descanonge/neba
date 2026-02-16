"""Configuration loaders bases."""

from __future__ import annotations

import logging
import typing as t
from collections import abc
from copy import deepcopy
from os import path

from traitlets.traitlets import HasTraits, TraitError, TraitType, Union
from traitlets.utils.sentinel import Sentinel

from neba.config.types import ConfigParsingError, MultipleConfigKeyError

if t.TYPE_CHECKING:
    from neba.config.application import Application
    from neba.config.section import Section

Undefined = Sentinel(
    "Undefined", "neba", "Configuration value not (yet) set or parsed."
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

    def __str__(self) -> str:
        s = [str(self.get_value())]
        if self.origin is not None:
            s.append(f"({self.origin})")
        return " ".join(s)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"

    @property
    def path(self) -> list[str]:
        """List of the dot-separated names of the key."""
        return self.key.split(".")

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

        This method tries to handle containers and union more gracefully. If all options
        have been tried and no parsing was successful the function will raise.
        """

        def _try(func: str, trait: TraitType, src: str | abc.Sequence[str]) -> bool:
            try:
                self.value = getattr(trait, func)(src)
                return True
            except (AttributeError, TraitError, ValueError):
                return False

        def try_item(src: str, trait: TraitType) -> bool:
            return _try("from_string", trait, src)

        def try_list(src: abc.Sequence[str], trait: TraitType) -> bool:
            return _try("from_string_list", trait, src)

        def _parse(src: str | abc.Sequence[str], trait: TraitType) -> bool:
            src = [src] if isinstance(src, str) else list(src)

            if hasattr(trait, "from_string_list") and try_list(src, trait):
                return True

            # Handle Union with lists
            if isinstance(trait, Union):
                for inner in trait.trait_types:
                    if _parse(src, inner):
                        return True

            # Handle everything else
            if len(src) == 1 and try_item(src[0], trait):
                return True

            return False

        if self.trait is None:
            raise ConfigParsingError(
                f"Cannot parse key '{self.key}' without a corresponding trait."
            )

        if _parse(self.input, self.trait):
            return

        traitname = self.trait.__class__.__name__
        raise ConfigParsingError(
            f"Could not parse '{self.input}' for trait '{self.key}' ({traitname})."
        )


class ConfigLoader:
    """Abstract ConfigLoader.

    Define the public API that will be used by the
    :class:`Application<.application.Application>` object, as well as some common logic.

    Parameters
    ----------
    app
        Parent application that created this loader.
    log
        Logger instance.
    """

    app: Application
    log: logging.Logger
    config: dict[str, ConfigValue]
    """Configuration dictionnary mapping keys to ConfigValues.

    It should be a flat dictionnary.
    """

    def __init__(self, app: Application, log: logging.Logger | None = None):
        self.app = app
        """Parent application that created this loader.

        It will be used to deal with exceptions, and to resolve/normalize the config
        once loaded.
        """
        if log is None:
            log = logging.getLogger(__name__)
        self.log = log
        self.config = {}

    def clear(self) -> None:
        """Empty the config."""
        self.config.clear()

    def add(self, cv: ConfigValue):
        """Add key to configuration dictionnary.

        Raises
        ------
        MultipleConfigKeyError
            If the key is already present in the current configuration.
        """
        if cv.key in self.config:
            raise MultipleConfigKeyError(cv.key, [self.config[cv.key], cv])
        self.config[cv.key] = cv

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
        with self.app.hold_trait_notifications():
            for conf_value in self.load_config(*args, **kwargs):
                if resolve:
                    conf_value = self.app.resolve_config_value(conf_value)
                if apply_application_traits:
                    self.apply_application_trait(conf_value)
                self.add(conf_value)

        return self.config

    def apply_application_trait(self, cv: ConfigValue):
        """Apply config for Application."""
        if len(cv.path) == 1 and cv.key in self.app.trait_names():
            traitname = cv.path[0]
            cv.trait = self.app.traits()[traitname]
            if cv.value is Undefined:
                cv.parse()
            setattr(self.app, traitname, cv.get_value())

    def load_config(self, *args, **kwargs) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from a source.

        :Not implemented:
        """
        raise NotImplementedError


class SerializerDefault:
    """Serialize trait values for config files."""

    def default(self, trait: TraitType, key: str | None = None) -> t.Any:
        """Serialize the default value of the trait."""
        raise NotImplementedError()

    def value(self, trait: TraitType, value: t.Any, key: str | None = None) -> t.Any:
        """Serialize the current value of the trait."""
        raise NotImplementedError()


class FileLoader(ConfigLoader):
    """Load config from a file.

    Common logic goes here.

    Parameters
    ----------
    filename
        Path of configuration file to load.
    """

    serializer = SerializerDefault()

    def __init__(self, app: Application, filename: str, *args, **kwargs) -> None:
        super().__init__(app, *args, **kwargs)
        self.filename = filename
        self.full_filename = path.abspath(filename)

    def write(self, fp: t.IO, comment: t.Any = None):
        """Write a configuration file corresponding to the loader config.

        Parameters
        ----------
        fp
            File stream to write to.
        comment
            Include more or less information as comments. Can be one of:

            * full: all information about traits is included
            * no-help: trait help attribute is not included
            * none: no information is included, only the key and default value

            Note that the line containing the key and default value, for instance
            ``traitname = 2`` will be commented since we do not need to parse/load the
            default value.
        """
        raise NotImplementedError()


class DictLikeLoaderMixin(ConfigLoader):
    """Load a configuration from a mapping.

    As there are no way to differentiate between a mapping for a dictionary trait and
    one for a nested section, we need to check the existing keys before resolving. We
    only look for existing subsections and aliases, otherwise we assume this is a
    dict-like value.
    """

    def resolve_mapping(
        self, input: abc.Mapping, origin: str | None = None
    ) -> abc.Iterator[ConfigValue]:
        """Flatten an input nested mapping."""

        def recurse(
            d: abc.Mapping, section: type[Section], key: list[str]
        ) -> abc.Iterator[ConfigValue]:
            for k, v in d.items():
                # key might be dot-separated
                for subkey in k.split("."):
                    if subkey in section._subsections:
                        assert isinstance(v, abc.Mapping)
                        yield from recurse(
                            v, section._subsections[subkey].klass, key + [subkey]
                        )

                    elif subkey in section.aliases:
                        assert isinstance(v, abc.Mapping)
                        # resolve alias
                        sub = section
                        alias = section.aliases[subkey].split(".")
                        for al in alias:
                            sub = sub._subsections[al].klass
                        yield from recurse(v, sub, key + alias)

                    else:
                        fullkey = ".".join(key + [subkey])
                        value = ConfigValue(v, fullkey, origin=origin)
                        # no parsing, directly to values
                        value.value = value.input
                        yield value

        yield from recurse(input, self.app.__class__, [])


class DictLoader(DictLikeLoaderMixin):
    """Loader for mappings."""

    def load_config(
        self, input: abc.Mapping, *args, **kwargs
    ) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from a nested mapping."""
        yield from self.resolve_mapping(input)
