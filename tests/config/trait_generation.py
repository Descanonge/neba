"""Generate traits.

We use trait generators objects. They can generate a trait on their own. For composed
traits (example a List of ...) this is a bit more difficult. In some cases we can
easily get non-sensical or problematic traits (Union typically). To ease things any
trait generator that needs inner(s) trait(s) should receive correpsonding generator(s)
at initialization. That means we must create by hand the recursive organization of
composed traits, to help a bit.

The module contains generator for all basic traits. And functions to generate traits
out of thin air, or obtain generator from existing traits.
"""

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


class DummyClass:
    """Used for Instance and Type traits."""

    def __init__(self, value: int):
        self.value = value

    def __eq__(self, other) -> bool:
        return self.value == other.value

    def __repr__(self):
        return f"{self.__class__.__name__}()"


DummySubclass = type("DummySubclass", (DummyClass,), {})


class TraitGenerator(t.Generic[T_Trait]):
    """Generate a trait and valid values.

    This class is the base for every trait type.

    Parameters
    ----------
    draw_default
        Wether to draw a default value (true) or not.
    allow_none
        Same as trait parameter. If True, the value strategy can draw None.
    kwargs
        Will be passed when instantiating trait.
    """

    traittype: type[T_Trait]
    """Type of the trait to generate. Each class generates one type."""

    def __init__(self, draw_default: bool = True, allow_none: bool = False, **kwargs):
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
        """Return a strategy to pick an appropriate default value.

        By default this is the same as :meth:`st_value`.
        """
        return self.st_value()

    def draw_pre_instance(self, draw: Drawer, **kwargs) -> dict[str, t.Any]:
        """Generate keyword arguments for instantiation.

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


class BoolGen(TraitGenerator[Bool]):
    """Bool Generator."""

    traittype = Bool

    def _st_value(self) -> st.SearchStrategy[bool]:
        return st.booleans()


class IntGen(TraitGenerator[Int]):
    """Integer Generator."""

    traittype = Int

    def _st_value(self) -> st.SearchStrategy[int]:
        return st.integers()


class FloatGen(TraitGenerator[Float]):
    """Float Generator."""

    traittype = Float

    def _st_value(self) -> st.SearchStrategy[float]:
        return st.floats(allow_nan=False, allow_infinity=False)


class UnicodeGen(TraitGenerator[Unicode]):
    """Unicode Generator.

    Avoid symbols, they can throw parsers off.
    """

    traittype = Unicode

    def _st_value(self) -> st.SearchStrategy[str]:
        return st.text(
            max_size=32,
            alphabet=st.characters(categories=["L", "M", "N", "S", "Zs"]),
        )


class EnumGen(TraitGenerator[Enum]):
    """Enum Generator.

    Values must be supplied for the Enum.
    """

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
    """Generator with inner(s) trait(s)."""


class ContainerGen(ComposedGenerator[T_Trait]):
    """Single inner trait generator (List and Set).

    A generator must be supplied for the inner trait.
    """

    def __init__(self, inner_gen: TraitGenerator, **kwargs):
        super().__init__(**kwargs)
        self.inner_gen = inner_gen

    def draw_inner(self, draw: Drawer, **kwargs) -> TraitType:
        return self.inner_gen.draw_instance(draw, **kwargs)

    def draw_instance(self, draw: Drawer, **kwargs) -> T_Trait:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(self.draw_inner(draw), **kwargs)


class ListGen(ContainerGen[List]):
    """List Generator."""

    traittype: type[List] = List

    def st_default(self) -> st.SearchStrategy[list]:
        return st.lists(self.inner_gen.st_value())

    def _st_value(self) -> st.SearchStrategy[list]:
        return st.lists(self.inner_gen.st_value())


class SetGen(ContainerGen[Set]):
    """List Generator."""

    traittype = Set

    def st_default(self) -> st.SearchStrategy[set]:
        return st.sets(self.inner_gen.st_value())

    def _st_value(self) -> st.SearchStrategy[set]:
        return st.sets(self.inner_gen.st_value())


class ClassGen(ComposedGenerator[T_Trait]):
    """Class related Generator (Instance and Type).

    Store the target class.
    """

    def __init__(self, klass, **kwargs):
        super().__init__(**kwargs)
        self.klass = klass

    def get_subclass(self, name: str = "") -> type:
        """Generate subclass.

        The only base is :attr:`klass`, and no definitions are added.

        Parameters
        ----------
        name
            Name of the subclass. If left empty, "_subclass" will be added to the
            current class.
        """
        return self.klass
        # if not name:
        #     name = self.klass.__name__ + "_subclass"
        # cls = type(name, (self.klass,), {})
        # return cls


class InstanceGen(ClassGen[Instance]):
    """Instance Generator.

    Can return an instance of specified klass or one of a generated subclass.
    """

    traittype: type[Instance] = Instance

    def _st_value(self) -> st.SearchStrategy:
        @st.composite
        def strat(draw: Drawer):
            klass = draw(st.sampled_from([self.klass, self.get_subclass()]))
            return draw(st.builds(klass))

        return strat()


class TypeGen(ClassGen[Type]):
    """Type Generator.

    Does not handle str specifically well. If klass is a string, just return this value.
    """

    traittype = Type

    def _st_value(self) -> st.SearchStrategy[type]:
        if isinstance(str, self.klass):
            return st.just(self.klass)
        # clsname = f"{self.klass.__module__}.{self.klass.__qualname__}"
        return st.sampled_from([self.klass, self.get_subclass()])


class UnionGen(ComposedGenerator[Union]):
    """Union generator.

    Inner traits must be supplied.
    """

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
    """Dict generator.

    Key and value generator must be supplied.
    """

    traittype = Dict

    def __init__(self, key_gen: TraitGenerator, value_gen: TraitGenerator, **kwargs):
        super().__init__(**kwargs)
        self.key_gen = key_gen
        self.value_gen = value_gen

    def _st_value(self) -> st.SearchStrategy[dict]:
        return st.dictionaries(self.key_gen.st_value(), self.value_gen.st_value())


registered_gens: list[type[TraitGenerator]] = [BoolGen, IntGen, FloatGen, UnicodeGen]


def st_trait_gen(**kwargs) -> st.SearchStrategy[TraitGenerator]:
    """Strategy to obtain a random TraitGenerator among simple ones.

    Arguments are passed to whatever TraitGenerator is picked.
    Only select "simple" traits: Bool, Float, Int, etc. Not List, Set, ... with nested
    traits.
    """

    @st.composite
    def strat(draw: Drawer):
        gen_type = draw(st.sampled_from(list(registered_gens)))
        return gen_type(**kwargs)

    return strat()


TRAIT_TO_GEN: dict[type[TraitType], type[TraitGenerator]] = {
    Bool: BoolGen,
    Int: IntGen,
    Float: FloatGen,
    Unicode: UnicodeGen,
    Enum: EnumGen,
    List: ListGen,
    Set: SetGen,
    Dict: DictGen,
    Tuple: TupleGen,
    Instance: InstanceGen,
    Type: TypeGen,
    Union: UnionGen,
}


def trait_to_gen(
    trait: T_Trait, allow_none: bool | None = None, **kwargs
) -> TraitGenerator[T_Trait]:
    """Return TraitGenerator instance corresponding to trait.

    Use information present in the trait to inform the generators, inner trait types
    for instance.

    For List and Set, if the inner trait is missing, `Int()` will be used.
    For Dict, if the key or value traits are missing, `Unicode()` and `Int()` will be
    used for the keys and values respectively.
    For Instance and Trrait, if the klass is missing, `object` will be used.

    Kwargs is unused.
    """
    if allow_none is None:
        allow_none = trait.allow_none
    kw = dict(draw_default=False, allow_none=allow_none)

    cls = type(trait)

    if isinstance(trait, Bool | Int | Float | Unicode):
        return TRAIT_TO_GEN[cls](**kw)

    if isinstance(trait, Enum):
        assert trait.values is not None
        return EnumGen(trait.values, **kw)  # type: ignore[return-value]

    if isinstance(trait, List | Set):
        inner = trait._trait
        if inner is None:
            inner = Int()
        gen = TRAIT_TO_GEN[cls]
        assert issubclass(gen, ContainerGen)
        return gen(trait_to_gen(inner), **kw)

    if isinstance(trait, Dict):
        key_trait = trait._key_trait
        val_trait = trait._value_trait
        if key_trait is None:
            key_trait = Unicode()
        if val_trait is None:
            val_trait = Int()
        return DictGen(
            key_gen=trait_to_gen(key_trait, **kw),
            value_gen=trait_to_gen(val_trait),
            **kw,
        )  # type: ignore[return-value]

    if isinstance(trait, Union):
        return UnionGen(  # type: ignore[return-value]
            [trait_to_gen(t, **kw) for t in trait.trait_types], **kw
        )

    if isinstance(trait, Tuple):
        return TupleGen(  # type: ignore[return-value]
            *[trait_to_gen(t, **kw) for t in trait._traits], **kw
        )

    if isinstance(trait, Instance | Type):
        klass = trait.klass
        if klass is None:
            klass = object
        gen = TRAIT_TO_GEN[cls]
        assert issubclass(gen, ClassGen)
        return gen(klass, **kw)

    raise TypeError(f"Cannot find generator for trait type '{type(trait)}'")


def trait_to_strat(trait: TraitType, **kwargs) -> st.SearchStrategy:
    gen = trait_to_gen(trait, **kwargs)
    return gen.st_value()


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
