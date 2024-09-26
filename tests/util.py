import keyword
import typing as t
from collections import abc

from hypothesis import strategies as st
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

from data_assistant.config import Scheme, subscheme

P = t.TypeVar("P")


class Drawer(t.Protocol):
    """Drawing function."""

    def __call__(self, __strat: st.SearchStrategy[P]) -> P: ...


T_Trait = t.TypeVar("T_Trait", bound=TraitType)


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

    def __init__(self, has_default: bool | None = None, *args, **kwargs):
        self.has_default = has_default
        self.kwargs = kwargs

    def _draw_def_value(self, draw: Drawer) -> t.Any:
        """Return an actual default value if possible."""
        return draw(self.get_value_strategy())

    def draw_def_value(self, draw: Drawer) -> t.Any | None:
        """Draw a default value or None depending on value of *self.has_default*."""
        if self.has_default is None:
            self.has_default = draw(st.booleans())

        if self.has_default:
            return self._draw_def_value(draw)
        return None

    def draw_pre_instance(self, draw: Drawer, **kwargs) -> dict[str, t.Any]:
        """Generate keyword arguments for instanciation.

        Merge attribute :attr:`kwargs` and argument *kwargs*, draw default value and
        add to the kwargs.
        """
        kwargs = self.kwargs | kwargs
        def_val = self.draw_def_value(draw)
        if def_val is not None:
            kwargs["default_value"] = def_val
        else:
            kwargs["allow_none"] = True
        return kwargs

    def draw_instance(self, draw: Drawer, **kwargs) -> T_Trait:
        """Draw an instance of the trait."""
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(**kwargs)

    def get_value_strategy(self) -> st.SearchStrategy:
        """Return a strategy to pick an appopriate value."""
        raise NotImplementedError()


class BoolGen(TraitGenerator[Bool]):
    traittype = Bool

    def get_value_strategy(self) -> st.SearchStrategy[bool]:
        return st.booleans()


class IntGen(TraitGenerator[Int]):
    traittype = Int

    def get_value_strategy(self) -> st.SearchStrategy[int]:
        return st.integers()


class FloatGen(TraitGenerator[Float]):
    traittype = Float

    def get_value_strategy(self) -> st.SearchStrategy[float]:
        return st.floats(allow_nan=False, allow_infinity=False)


class UnicodeGen(TraitGenerator[Unicode]):
    traittype = Unicode

    def get_value_strategy(self) -> st.SearchStrategy[str]:
        return st.text(max_size=32)


class EnumGen(TraitGenerator[Enum]):
    traittype = Enum

    def __init__(self, values: abc.Sequence[t.Any], **kwargs):
        self.values = list(values)
        super().__init__(**kwargs)

    def draw_instance(self, draw: Drawer, **kwargs) -> Enum:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(values=self.values, **kwargs)

    def get_value_strategy(self):
        return st.sampled_from(self.values)


class ComposedGenerator(TraitGenerator[T_Trait]):
    pass


class ContainerGen(ComposedGenerator[T_Trait]):
    def __init__(self, inner_gen: TraitGenerator[T_Trait], **kwargs):
        super().__init__(**kwargs)
        self.inner_gen = inner_gen

    def draw_inner(self, draw: Drawer, **kwargs) -> T_Trait:
        return self.inner_gen.draw_instance(draw, **kwargs)

    def draw_instance(self, draw: Drawer, **kwargs) -> T_Trait:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(self.draw_inner(draw), **kwargs)


T = t.TypeVar("T")


class ListGen(t.Generic[T], ContainerGen[List]):
    traittype: type[List[T]] = List

    def _draw_def_value(self, draw: Drawer) -> list[T]:
        return draw(st.lists(self.inner_gen.get_value_strategy()))

    def get_value_strategy(self) -> st.SearchStrategy[list[T]]:
        return st.lists(self.inner_gen.get_value_strategy())


class SetGen(t.Generic[T], ContainerGen[Set]):
    # traitlets.traitlets.Set is not Generic
    traittype = Set

    def _draw_def_value(self, draw: Drawer) -> set[T]:
        return draw(st.sets(self.inner_gen.get_value_strategy()))

    def get_value_strategy(self) -> st.SearchStrategy[set[T]]:
        return st.sets(self.inner_gen.get_value_strategy())


class InstanceGen(t.Generic[T], ContainerGen[Instance]):
    traittype: type[Instance[T]] = Instance


class TypeGen(t.Generic[T], ContainerGen[Type]):
    traittype = Type


class UnionGen(ComposedGenerator[Union]):
    traittype = Union

    def __init__(self, inner_gens: abc.Sequence[TraitGenerator], **kwargs):
        super().__init__(**kwargs)
        self.inner_gens = list(inner_gens)

    def draw_inners(self, draw: Drawer, **kwargs) -> list[TraitType]:
        return [g.draw_instance(draw, **kwargs) for g in self.inner_gens]

    def _draw_def_value(self, draw: Drawer) -> t.Any | None:
        """Draw default value.

        For Union it's the first not-None default value of the inner traits.
        Technically a default value could also be input as keyword argument but for now
        it will do.
        """
        default = None
        for gen in self.inner_gens:
            default = gen.draw_def_value(draw)
            if default is not None:
                break
        return default

    def draw_instance(self, draw: Drawer, **kwargs) -> Union:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(self.draw_inners(draw), **kwargs)

    def get_value_strategy(self) -> st.SearchStrategy:
        """Value Strategy.

        We select one of the inner traits at random to generate a value.
        """
        return st.one_of([gen.get_value_strategy() for gen in self.inner_gens])


class TupleGen(ComposedGenerator[Tuple]):
    """Tuple trait generator.

    Always pass one or more traits. Tuple traits are always the length of the inner
    traits. This is different from List traits which have a single trait and their
    length is unspecified by default.
    """

    traittype = Tuple

    def __init__(self, *inner_gens: TraitGenerator, **kwargs):
        super().__init__(**kwargs)
        self.inner_gens = list(inner_gens)

    def draw_inners(self, draw: Drawer, **kwargs) -> list[TraitType]:
        return [g.draw_instance(draw, **kwargs) for g in self.inner_gens]

    def _draw_def_value(self, draw: Drawer) -> tuple[t.Any]:
        return tuple([gen._draw_def_value(draw) for gen in self.inner_gens])

    def draw_instance(self, draw: Drawer, **kwargs) -> Tuple:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(*self.draw_inners(draw), **kwargs)

    def get_value_strategy(self) -> st.SearchStrategy[tuple]:
        return st.tuples(*[gen.get_value_strategy() for gen in self.inner_gens])


K = t.TypeVar("K")
V = t.TypeVar("V")


class DictGen(t.Generic[K, V], ComposedGenerator[Dict]):
    traittype = Dict


SIMPLE_TRAIT_GENS: list[type[TraitGenerator]] = [
    BoolGen,
    FloatGen,
    IntGen,
    UnicodeGen,
    EnumGen,
]
COMPOSED_TRAIT_GENS: list[type[TraitGenerator]] = [ListGen, SetGen, TupleGen, UnionGen]


def st_trait_gen(**kwargs) -> st.SearchStrategy[TraitGenerator]:
    """Strategy to obtain a random TraitGenerator among simple ones.

    Arguments are passed to whatever TraitGenerator is picked.
    Only select "simple" traits: Bool, Float, Int, etc. Not List, Set, ... with nested
    traits.
    """

    @st.composite
    def strat(draw: Drawer):
        gen_type = draw(st.sampled_from(SIMPLE_TRAIT_GENS))
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


valid = "".join(chr(i) for i in range(97, 123))
valid += valid.upper()
valid += "".join(str(i) for i in range(10))
valid += "_"
varname_st = (
    st.text(alphabet=valid, min_size=1, max_size=16)
    .filter(lambda s: not s.startswith("__"))
    .filter(lambda s: s.isidentifier())
    .filter(lambda s: not keyword.iskeyword(s))
)


class SchemeGenerator:
    """Generate a Scheme."""

    def __init__(
        self,
        clsname: str = "",
        traits_gens: dict[str, TraitGenerator] | None = None,
        subschemes: dict[str, "SchemeGenerator"] | None = None,
    ):
        self.clsname = clsname
        self.nest_level: int

        if traits_gens is None:
            traits_gens = {}
        if subschemes is None:
            subschemes = {}
        self.traits_gens: dict[str, TraitGenerator] = traits_gens
        self.subschemes: dict[str, SchemeGenerator] = subschemes

        self.traits: dict[str, TraitType] = {}

    def get_cls(self) -> type[Scheme]:
        return type(self.clsname, (Scheme,), dict(self.traits))

    def draw_traits(self, draw: Drawer, **kwargs):
        self.traits = {
            name: gen.draw_instance(draw).tag(config=True)
            for name, gen in self.traits_gens.items()
        }

        for sub_gen in self.subschemes.values():
            sub_gen.draw_traits(draw)

        for name, sub_gen in self.subschemes.items():
            cls = sub_gen.get_cls()
            self.traits[name] = subscheme(cls)

    def draw_instance(self, draw: Drawer) -> Scheme:
        self.draw_traits(draw)
        return self.get_cls()()

    def st_inst(self) -> st.SearchStrategy[Scheme]:
        @st.composite
        def strat(draw: Drawer) -> Scheme:
            return self.draw_instance(draw)

        return strat()

    def st_values_single(self) -> st.SearchStrategy[dict[str, t.Any]]:
        """Get mapping of values for every trait on this level."""

        @st.composite
        def strat(draw: Drawer) -> dict[str, t.Any]:
            values = {
                name: draw(gen.get_value_strategy())
                for name, gen in self.traits_gens.items()
                if name not in self.subschemes
            }
            return values

        return strat()

    def st_values(self) -> st.SearchStrategy[dict[str, t.Any]]:
        """Get mapping of values for every trait."""

        def new_path(old: str, new: str) -> str:
            if not old:
                return new
            return f"{old}.{new}"

        @st.composite
        def strat(draw: Drawer) -> dict[str, t.Any]:
            def recurse(gen: t.Self) -> dict[str, t.Any]:
                values = draw(gen.st_values_single())
                for sub_name, sub_gen in gen.subschemes.items():
                    values[sub_name] = recurse(sub_gen)
                return values

            return recurse(self)

        return strat()


def st_scheme_cls(
    scheme_gen: SchemeGenerator, **kwargs
) -> st.SearchStrategy[type[Scheme]]:
    @st.composite
    def strat(draw) -> type[Scheme]:
        scheme_gen.draw_traits(draw)
        cls = scheme_gen.get_cls()
        return cls

    return strat()


def st_scheme_instance(
    scheme_gen: SchemeGenerator, **kwargs
) -> st.SearchStrategy[Scheme]:
    @st.composite
    def strat(draw) -> Scheme:
        scheme_gen.draw_traits(draw)
        cls = scheme_gen.get_cls()
        values = draw(scheme_gen.st_values())
        return cls.instanciate_recursively(values)

    return strat()


def st_scheme_instances(
    scheme_gen: SchemeGenerator, n: int = 2, **kwargs
) -> st.SearchStrategy[tuple[Scheme, ...]]:
    @st.composite
    def strat(draw: Drawer) -> tuple[Scheme, ...]:
        scheme_gen.draw_traits(draw)
        cls = scheme_gen.get_cls()
        instances = []
        for _ in range(n):
            values = draw(scheme_gen.st_values())
            inst = cls.instanciate_recursively(values)
            instances.append(inst)
        return tuple(instances)

    return strat()
