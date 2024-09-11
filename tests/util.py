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

from data_assistant.config import Scheme

SIMPLE_TRAIT_TYPES: list[type[TraitType]] = [Bool, Float, Int, Unicode]
COMPOSED_TRAIT_TYPES: list[type[TraitType]] = [Dict, Enum, Instance, List, Type, Union]
MAX_INNER_NUM = 3

P = t.TypeVar("P")


class Drawer(t.Protocol):
    def __call__(self, __strat: st.SearchStrategy[P]) -> P: ...


T = t.TypeVar("T", bound=TraitType)


class TraitGenerator(t.Generic[T]):
    """Generate a trait.

    Parameters
    ----------
    traittype
        Type of the trait to generate
    has_default
        Wether to draw a default value (true) or not. If left to None, its value will be
        picked at random by hypothesis.
    kwargs
        Will be passed when instanciating trait.
    """

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        return st.just(cls(has_default=has_default, **kwargs))

    traittype: type[T]

    def __init__(self, has_default: bool | None = None, **kwargs):
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
        return kwargs

    def draw_instance(self, draw: Drawer, **kwargs) -> T:
        """Draw an instance of the trait."""
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(**kwargs)

    def get_value_strategy(self) -> st.SearchStrategy:
        """Return a strategy to pick an appopriate value."""
        raise NotImplementedError()


class TraitGeneratorBool(TraitGenerator[Bool]):
    traittype = Bool

    def get_value_strategy(self) -> st.SearchStrategy[bool]:
        return st.booleans()


class TraitGeneratorInt(TraitGenerator[Int]):
    traittype = Int

    def get_value_strategy(self) -> st.SearchStrategy[int]:
        return st.integers()


class TraitGeneratorFloat(TraitGenerator[Float]):
    traittype = Float

    def get_value_strategy(self) -> st.SearchStrategy[float]:
        return st.floats(allow_nan=False, allow_infinity=False)


class TraitGeneratorUnicode(TraitGenerator[Unicode]):
    traittype = Unicode

    def get_value_strategy(self) -> st.SearchStrategy[str]:
        return st.text(max_size=32)


class TraitGeneratorEnum(TraitGenerator[Enum]):
    traittype = Enum

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        @st.composite
        def strat(draw: Drawer):
            typ = draw(st.sampled_from(SIMPLE_TRAIT_GENS))
            values = draw(st.lists(typ().get_value_strategy(), unique=True, min_size=1))
            return cls(has_default=has_default, values=values, **kwargs)

        return strat()

    def __init__(self, *args, values: abc.Sequence[t.Any], **kwargs):
        super().__init__(*args, **kwargs)
        self.values = list(values)

    def _draw_def_value(self, draw: Drawer) -> t.Any:
        return draw(self.get_value_strategy())

    def draw_instance(self, draw: Drawer, **kwargs) -> Enum:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(values=self.values, **kwargs)

    def get_value_strategy(self):
        return st.sampled_from(self.values)


class TraitGeneratorInner(TraitGenerator[T]):
    """Single inner trait.

    For Instance, Type, List, Set
    """

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        def make(draw: Drawer, typ: TraitGenerator):
            inner = draw(
                typ.create(
                    has_default=has_default,
                    max_rec_level=max_rec_level,
                    _rec_level=_rec_level + 1,
                    **kwargs,
                )
            )
            return cls(has_default=has_default, inner_gen=inner, **kwargs)

        @st.composite
        def strat_simple(draw: Drawer):
            typ = draw(st.sampled_from(SIMPLE_TRAIT_GENS))
            return make(draw, typ)

        @st.composite
        def strat_complex(draw: Drawer):
            typ = draw(st.sampled_from(SIMPLE_TRAIT_GENS + COMPOSED_TRAIT_GENS))
            return make(draw, typ)

        if _rec_level >= max_rec_level:
            return strat_simple()
        return strat_complex()

    def __init__(self, *args, inner_gen: TraitGenerator, **kwargs):
        super().__init__(*args, **kwargs)
        self.inner_gen = inner_gen
        inner_gen.has_default = False

    def draw_inner(self, draw: Drawer, **kwargs) -> TraitType:
        return self.inner_gen.draw_instance(draw, **kwargs)

    def draw_instance(self, draw: Drawer, **kwargs) -> T:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(self.draw_inner(draw), **kwargs)


class TraitGeneratorList(TraitGeneratorInner[List]):
    traittype = List

    def _draw_def_value(self, draw: Drawer) -> list[t.Any]:
        return draw(st.lists(self.inner_gen.get_value_strategy()))

    def get_value_strategy(self) -> st.SearchStrategy[list]:
        return st.lists(self.inner_gen.get_value_strategy())


class TraitGeneratorSet(TraitGeneratorInner[Set]):
    traittype = Set

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        return super().create(
            has_default=has_default, max_rec_level=0, _rec_level=1, **kwargs
        )

    def _draw_def_value(self, draw: Drawer) -> set[t.Any]:
        return draw(st.sets(self.inner_gen.get_value_strategy()))

    def get_value_strategy(self) -> st.SearchStrategy[set]:
        return st.sets(self.inner_gen.get_value_strategy())


class TraitGeneratorInners(TraitGenerator[T]):
    """Multiple inner traits.

    For Union, Tuple.
    """

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        def make(draw: Drawer, gen_types):
            inners = [
                draw(
                    s.create(
                        has_default=has_default,
                        max_rec_level=max_rec_level,
                        _rec_level=_rec_level + 1,
                    )
                )
                for s in gen_types
            ]
            return cls(has_default=has_default, inner_gens=inners, **kwargs)

        @st.composite
        def strat_simple(draw: Drawer):
            gen_types = draw(
                st.lists(
                    st.sampled_from(SIMPLE_TRAIT_GENS),
                    min_size=1,
                    max_size=MAX_INNER_NUM,
                )
            )
            return make(draw, gen_types)

        @st.composite
        def strat_complex(draw: Drawer):
            gen_types = draw(
                st.lists(
                    st.sampled_from(SIMPLE_TRAIT_GENS + COMPOSED_TRAIT_GENS),
                    min_size=1,
                    max_size=MAX_INNER_NUM,
                )
            )
            return make(draw, gen_types)

        if _rec_level >= max_rec_level:
            return strat_simple()
        return strat_complex()

    def __init__(self, *args, inner_gens: abc.Sequence[TraitGenerator], **kwargs):
        super().__init__(*args, **kwargs)
        self.inner_gens = list(inner_gens)

    def draw_inners(self, draw: Drawer, **kwargs) -> list[TraitType]:
        return [g.draw_instance(draw, **kwargs) for g in self.inner_gens]


class TraitGeneratorUnion(TraitGeneratorInners[Union]):
    traittype = Union

    def _draw_def_value(self, draw: Drawer) -> t.Any | None:
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
        return st.one_of([gen.get_value_strategy() for gen in self.inner_gens])


class TraitGeneratorTuple(TraitGeneratorInners[Tuple]):
    traittype = Tuple

    def _draw_def_value(self, draw: Drawer) -> tuple[t.Any]:
        return tuple([gen._draw_def_value(draw) for gen in self.inner_gens])

    def draw_instance(self, draw: Drawer, **kwargs) -> Tuple:
        kwargs = self.draw_pre_instance(draw, **kwargs)
        return self.traittype(*self.draw_inners(draw), **kwargs)

    def get_value_strategy(self) -> st.SearchStrategy[tuple]:
        return st.tuples(*[gen.get_value_strategy() for gen in self.inner_gens])


SIMPLE_TRAIT_GENS: list[type[TraitGenerator]] = [
    TraitGeneratorBool,
    TraitGeneratorFloat,
    TraitGeneratorInt,
    TraitGeneratorUnicode,
]
COMPOSED_TRAIT_GENS: list[type[TraitGenerator]] = [
    TraitGeneratorEnum,
    TraitGeneratorList,
    TraitGeneratorSet,
    TraitGeneratorTuple,
    TraitGeneratorUnion,
]


def st_trait_gen(
    composed: bool = True, has_default: bool | None = None, max_nested: int = 2
) -> st.SearchStrategy[TraitGenerator]:
    def make(draw: Drawer, gen_type: type[TraitGenerator]) -> TraitGenerator:
        gen = draw(gen_type.create(has_default=has_default, max_rec_level=max_nested))
        return gen

    @st.composite
    def strat_simple(draw: Drawer):
        gen_type = draw(st.sampled_from(SIMPLE_TRAIT_GENS))
        return make(draw, gen_type)

    @st.composite
    def strat_complex(draw: Drawer):
        gen_type = draw(st.sampled_from(SIMPLE_TRAIT_GENS + COMPOSED_TRAIT_GENS))
        return make(draw, gen_type)

    if composed:
        return strat_complex()
    return strat_simple()


def st_trait(**kwargs) -> st.SearchStrategy[TraitType]:
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
    MAX_TRAITS = 12

    def __init__(self, composed: bool = True):
        self.composed = composed
        self.traits_gens: abc.Mapping[str, TraitGenerator] = {}
        self.traits: abc.Mapping[str, TraitType] = {}
        self.clsname: str = ""

    def draw_cls(self, draw, **kwargs) -> type[Scheme]:
        traits_gens = draw(
            st.lists(
                st_trait_gen(composed=self.composed, **kwargs), max_size=self.MAX_TRAITS
            )
        )
        n_traits = len(traits_gens)
        names = draw(
            st.lists(varname_st, min_size=n_traits, max_size=n_traits, unique=True)
        )
        self.clsname = draw(
            varname_st.map(lambda s: s.replace("_", " ").title().replace(" ", ""))
        )
        self.traits_gens = {name: gen for name, gen in zip(names, traits_gens)}
        self.traits = {
            name: gen.draw_instance(draw).tag(config=True)
            for name, gen in self.traits_gens.items()
        }
        return self.get_cls()

    def get_cls(self) -> type[Scheme]:
        return type(self.clsname, (Scheme,), dict(self.traits))

    def draw_values(self, draw) -> abc.Mapping[str, t.Any]:
        """Get mapping of values for every trait."""
        values = {
            name: draw(gen.get_value_strategy())
            for name, gen in self.traits_gens.items()
        }
        return values


def st_scheme_cls(**kwargs) -> st.SearchStrategy[type[Scheme]]:
    scheme_gen = SchemeGenerator(**kwargs)

    @st.composite
    def strat(draw) -> type[Scheme]:
        return scheme_gen.draw_cls(draw)

    return strat()


def st_scheme_instance(**kwargs) -> st.SearchStrategy[Scheme]:
    scheme_gen = SchemeGenerator(**kwargs)

    @st.composite
    def strat(draw) -> Scheme:
        cls = scheme_gen.draw_cls(draw)
        values = scheme_gen.draw_values(draw)
        inst = cls(**values)
        return inst

    return strat()


def st_scheme_instances(n: int = 2, **kwargs) -> st.SearchStrategy[tuple[Scheme, ...]]:
    scheme_gen = SchemeGenerator(**kwargs)

    @st.composite
    def strat(draw) -> tuple[Scheme, ...]:
        cls = scheme_gen.draw_cls(draw)
        instances = []
        for _ in range(n):
            values = scheme_gen.draw_values(draw)
            instances.append(cls(**values))
        return tuple(instances)

    return strat()
