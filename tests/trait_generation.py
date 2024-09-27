import typing as t
from collections import abc

import hypothesis.strategies as st
from traitlets import (
    Bool,
    Dict,
    Enum,
    Float,
    Instance,
    Int,
    List,
    Set,
    TraitType,
    Tuple,
    Type,
    Unicode,
    Union,
)

from tests.util import Drawer, T_Trait


class TraitGenerator(t.Generic[T_Trait]):
    """Generate a trait, hold some info about it.

    Allows to get a strategy for values that should validate.
    This class is the base for every trait type.

    Parameters
    ----------
    has_default
        Wether to draw a default value (true) or not. If left to None, its value will be
        picked at random by hypothesis.
    kwargs
        Will be passed when instanciating trait.
    """

    traittype: type[T_Trait]
    """Type of the trait to generate. Each class generates one type."""

    def __init__(
        self, draw_default: bool = True, allow_none: bool = False, *args, **kwargs
    ):
        self.draw_default = draw_default
        self.allow_none = allow_none
        self.kwargs = kwargs

    def _st_value(self) -> st.SearchStrategy:
        """Return a strategy to pick an appropriate value.

        Modify this function in subclasses.
        """
        raise NotImplementedError()

    def st_value(self) -> st.SearchStrategy:
        """Return a strategy to pick an appropriate value.

        Takes into account :attr:`allow_none`.
        """
        if self.allow_none:
            return st.one_of(self._st_value(), st.none())
        return self._st_value()

    def st_default(self) -> st.SearchStrategy:
        """Return a strategy to pick an appropriate default value."""
        return self.st_value()

    def draw_pre_instance(self, draw: Drawer, **kwargs) -> dict[str, t.Any]:
        """Generate keyword arguments for instanciation.

        Merge attribute :attr:`kwargs` and argument *kwargs*, draw default value and
        add to the kwargs.
        """
        kwargs = self.kwargs | kwargs
        if self.draw_default:
            kwargs["default_value"] = draw(self.st_value())
        kwargs["allow_none"] = self.allow_none
        return kwargs

    def draw_instance(self, draw: Drawer, **kwargs) -> T_Trait:
        """Draw an instance of the trait."""
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(**kwargs)


TGen = t.TypeVar("TGen", bound=type[TraitGenerator])


registry: dict[str, type[TraitGenerator]] = {}


def register(cls: TGen) -> TGen:
    key = str(cls)
    registry[key] = cls
    return cls


@register
class BoolGen(TraitGenerator[Bool]):
    traittype = Bool

    def _st_value(self) -> st.SearchStrategy[bool]:
        return st.booleans()


@register
class IntGen(TraitGenerator[Int]):
    traittype = Int

    def _st_value(self) -> st.SearchStrategy[int]:
        return st.integers()


@register
class FloatGen(TraitGenerator[Float]):
    traittype = Float

    def _st_value(self) -> st.SearchStrategy[float]:
        return st.floats(allow_nan=False, allow_infinity=False)


@register
class UnicodeGen(TraitGenerator[Unicode]):
    traittype = Unicode

    def _st_value(self) -> st.SearchStrategy[str]:
        return st.text(max_size=32)


class EnumGen(TraitGenerator[Enum]):
    traittype = Enum

    def __init__(self, values: abc.Sequence[t.Any], **kwargs):
        self.values = list(values)
        super().__init__(**kwargs)

    def draw_instance(self, draw: Drawer, **kwargs) -> Enum:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(values=self.values, **kwargs)

    def _st_value(self):
        return st.sampled_from(self.values)


class ComposedGenerator(TraitGenerator[T_Trait]):
    pass


class ContainerGen(ComposedGenerator[T_Trait]):
    def __init__(self, inner_gen: TraitGenerator, **kwargs):
        super().__init__(**kwargs)
        self.inner_gen = inner_gen

    def draw_inner(self, draw: Drawer, **kwargs) -> TraitType:
        return self.inner_gen.draw_instance(draw, **kwargs)

    def draw_instance(self, draw: Drawer, **kwargs) -> T_Trait:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(self.draw_inner(draw), **kwargs)


class ListGen(ContainerGen[List]):
    traittype: type[List] = List

    def st_default(self) -> st.SearchStrategy[list]:
        return st.lists(self.inner_gen.st_value())

    def _st_value(self) -> st.SearchStrategy[list]:
        return st.lists(self.inner_gen.st_value())


class SetGen(ContainerGen[Set]):
    traittype = Set

    def st_default(self) -> st.SearchStrategy[set]:
        return st.sets(self.inner_gen.st_value())

    def _st_value(self) -> st.SearchStrategy[set]:
        return st.sets(self.inner_gen.st_value())


class InstanceGen(ContainerGen[Instance]):
    traittype: type[Instance] = Instance


class TypeGen(ContainerGen[Type]):
    traittype = Type


class UnionGen(ComposedGenerator[Union]):
    traittype = Union

    def __init__(self, inner_gens: abc.Sequence[TraitGenerator], **kwargs):
        super().__init__(**kwargs)
        self.inner_gens = list(inner_gens)

    def draw_inners(self, draw: Drawer, **kwargs) -> list:
        return [g.draw_instance(draw, **kwargs) for g in self.inner_gens]

    def st_default(self) -> st.SearchStrategy:
        """Draw default value.

        For Union it's the first not-None default value of the inner traits.
        Technically a default value could also be input as keyword argument but for now
        it will do.
        """

        @st.composite
        def strat(draw: Drawer):
            default = None
            for gen in self.inner_gens:
                default = draw(gen.st_default())
                if default is not None:
                    break
            return default

        return strat()

    def draw_instance(self, draw: Drawer, **kwargs) -> Union:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(self.draw_inners(draw), **kwargs)

    def _st_value(self) -> st.SearchStrategy:
        """Value Strategy.

        We select one of the inner traits at random to generate a value.
        """
        return st.one_of([gen.st_value() for gen in self.inner_gens])


class TupleGen(ComposedGenerator[Tuple]):
    """Tuple trait generator.

    Always pass one or more traits. Tuple traits are always the length of the inner
    traits. This is different from List traits which have a single trait and their
    length is unspecified by default.
    """

    # traitlets.Tuple is not generic
    traittype = Tuple

    def __init__(self, *inner_gens: TraitGenerator, **kwargs):
        super().__init__(**kwargs)
        self.inner_gens = list(inner_gens)

    def draw_inners(self, draw: Drawer, **kwargs) -> list:
        return [g.draw_instance(draw, **kwargs) for g in self.inner_gens]

    def st_default(self) -> st.SearchStrategy[tuple]:
        @st.composite
        def strat(draw: Drawer):
            return tuple([draw(gen.st_default()) for gen in self.inner_gens])

        return strat()

    def draw_instance(self, draw: Drawer, **kwargs) -> Tuple:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(*self.draw_inners(draw), **kwargs)

    def _st_value(self) -> st.SearchStrategy[tuple]:
        return st.tuples(*[gen.st_value() for gen in self.inner_gens])


class DictGen(ComposedGenerator[Dict]):
    traittype = Dict


def st_trait_gen(**kwargs) -> st.SearchStrategy[TraitGenerator]:
    """Strategy to obtain a random TraitGenerator among simple ones.

    Arguments are passed to whatever TraitGenerator is picked.
    Only select "simple" traits: Bool, Float, Int, etc. Not List, Set, ... with nested
    traits.
    """

    @st.composite
    def strat(draw: Drawer):
        gen_type = draw(st.sampled_from(list(registry.values())))
        return gen_type(**kwargs)

    return strat()


def st_trait(**kwargs) -> st.SearchStrategy[TraitType]:
    """Strategy for a random trait.

    Arguments are passed to the TraitGenerator initialization.
    Only select "simple" traits: Bool, Float, Int, etc. Not List, Set, ... with nested
    traits.
    """

    @st.composite
    def strat(draw) -> TraitType:
        gen = draw(st_trait_gen(**kwargs))
        trait = gen.draw_instance(draw)
        return trait

    return strat()
