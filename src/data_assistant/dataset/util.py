from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .dataset import DatasetAbstract


log = logging.getLogger(__name__)


class Module:
    TO_DEFINE_ON_DATASET: Sequence[str] = []

    auto_cache: dict[str, Callable] = {}

    def __init__(self, dataset: DatasetAbstract):
        self.dataset = dataset
        self.cache: dict[str, Any] = {}

    def run_on_dataset(self, method: str, *args, **kwargs):
        if hasattr(self.dataset, method) and callable(getattr(self.dataset, method)):
            func = getattr(self.dataset, method)

            # We use PARAMS_NAMES instead of allowed_params which contains
            # fixables, which can be missing in some operations
            missing = [p for p in self.dataset.PARAMS_NAMES
                       if p not in self.dataset.params]
            if missing:
                log.warning('Possibly missing parameters %s', str(missing))

            return func(*args, **kwargs)
        else:
            classname = self.dataset.__class__.__name__
            msg = f"{classname} has no callable method '{method}'."
            if method in self.TO_DEFINE_ON_DATASET:
                msg += f" You must subclass {classname} and define '{method}'."
            raise AttributeError(msg)

    def _reset_cached_properties(self) -> None:
        self.cache = {}

    def get_cached(self, key: str) -> Any:
        # If in cache, easy
        if key in self.cache:
            return self.cache[key]

        # If AutoCachedProperty, generate it
        if key in self.auto_cache:
            func = self.auto_cache[key]
            value = func()
            self.cache[key] = value
            return value

        raise KeyError(f"Key '{key}' not found in cache or auto_cache")


class add_auto_cached:

    def __init__(self, *properties: AutoCachedProperty):
        self.properties = properties

    def __call__(self, cls: type[Module]) -> type[Module]:
        for prop in self.properties:
            prop.add_to_cls(cls)
        return cls


class AutoCachedProperty:
    """Attribute that can be cached and automatically generated.

    Can generate automatically a property that will retrieve the value from
    cache (and if not in cache, will generate a new value and store it).
    The property will have the doc string specified by 'help'.
    """

    def __init__(
            self,
            name: str,
            generator: Callable | str,
            create_property: bool = True,
            help: str = ''
    ):
        self.name = name
        self.generator: str | Callable = generator
        self.create_property = create_property
        self.help = help

    def add_to_cls(self, cls: type[Module]) -> type[Module]:
        # Add generator to the class
        if isinstance(self.generator, str):
            gen = getattr(cls, self.generator)
        else:
            gen = self.generator
        cls.auto_cache[self.name] = gen

        # Add property
        if self.create_property:
            prop = self.get_auto_property(cls)
            setattr(cls, self.name, prop)

        return cls

    def get_auto_property(self, cls) -> property:
        # property is simple cache grab
        def auto_prop(obj):
            return obj.get_cached(self.name)

        # create documentation
        help = self.help
        if not help:
            help = f'{self.name} auto-cached property.'

        # get generator name nicely rendered
        if isinstance(self.generator, str):
            gen_name = f'{cls.__name__}.{self.generator}'
        elif (qname := getattr(self.generator, '__qualname__', '')):
            gen_name = qname
        else:
            gen_name = str(self.generator)

        footer = ('Auto-cached property: if not cached, its value will be '
                  f'retrieved (and cached) by {gen_name}.')

        auto_prop.__doc__ = help + '\n\n' + footer

        # Turn it into a property
        return property(auto_prop)
