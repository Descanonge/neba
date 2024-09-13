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

SIMPLE_TRAIT_TYPES: list[type[TraitType]] = [Bool, Float, Int, Unicode]
COMPOSED_TRAIT_TYPES: list[type[TraitType]] = [Dict, Enum, Instance, List, Type, Union]
MAX_INNER_NUM = 3

P = t.TypeVar("P")


class Drawer(t.Protocol):
    """Drawing function."""

    def __call__(self, __strat: st.SearchStrategy[P]) -> P: ...


T = t.TypeVar("T", bound=TraitType)


class TraitGenerator(t.Generic[T]):
    """Generate a trait, hold some info about it.

    Allows to get a strategy for values that should validate.

    This class is the base for every trait type. It is reused nearly as-is by "simple"
    traits: bool, int, float, unicode.

    Parameters
    ----------
    has_default
        Wether to draw a default value (true) or not. If left to None, its value will be
        picked at random by hypothesis.
    kwargs
        Will be passed when instanciating trait.
    """

    traittype: type[T]
    """Type of the trait to generate. Each class generates one type."""

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        """Return a strategy for a TraitGenerator instance.

        It allows to generate the arguments for each TraitGenerator.

        I separate strategies here (instead of passing a draw function around).
        This helps with nested traits (see documentation of those).
        """
        return st.just(cls(has_default=has_default, **kwargs))

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
        else:
            kwargs["allow_none"] = True
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
        """Generator strategy for Enum.

        We need values as input. They allow to define the trait, and create a valid
        strategy for generating values.

        We take a "simple" trait type and generate some number of values from it.
        """

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
    """Trait holding aingle inner trait.

    For: Instance, Type, List, Set
    """

    @classmethod
    def create(
        cls: type[t.Self],
        has_default: bool | None = None,
        max_rec_level: int = 2,
        _rec_level: int = 0,
        **kwargs,
    ) -> st.SearchStrategy[t.Self]:
        """Return strategy for TraitGenerator.

        We need to select an inner trait (which itself can be nested). When we hit a
        recursion limit we must only select simple Traits (bool, int, etc). It seems
        hypothesis really dislike to have to pick from lists that are selected
        dynamically. It detects a "Flaky Strategy" and "inconsistant data generation".
        For that reason I use two different strategies/functions.
        """

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
        """Return strategy for Set.

        Sets needs (via hypothesis st.sets) to have unique values. So they must be
        hashable, which is not the case for some nested types (set, list). For the
        moment I do not allow nesting for sets.
        """
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
        """Return strategy for traits generators that needs multiple inner traits.

        Same remarks as for TraitGeneratorInner: I use two different strategies instead
        of modifying the strategy at runtime (which hypothesis dislike in our case).
        """

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
    """Union generator.

    Note that inner traits are selected at random, so they won't necessarily be
    ordered sensibly. For parsing this can cause a trait to cast all value without
    letting other try. See traitlets doc. For now, it should do. I do not intend to
    test the traitlets package itself after all.
    """

    traittype = Union

    def _draw_def_value(self, draw: Drawer) -> t.Any | None:
        """Default value.

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


class TraitGeneratorTuple(TraitGeneratorInners[Tuple]):
    """Tuple trait generator.

    Always pass one or more traits. Tuple traits are always the length of the inner
    traits. This is different from List traits which have a single trait and their
    length is unspecified by default.
    """

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
    """Strategy to obtain a TraitGenerator.

    Parameters
    ----------
    composed
        If False, limit to simple traits types Int, Float, Bool, Unicode.
    max_nested
        Maximum nesting of traits if composed is True (List(Tuple([Int(), Set(Bool)])))
    """
    # Same trick, to avoid changing strategies dynamically, we create two different
    # strategies.

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
    """Strategy for a random trait.

    Arguments are passed to `.st_trait_gen`.
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

    MAX_TRAITS = 3
    MAX_SUBSCHEMES = 2
    MAX_NEST_LEVEL = 2

    def __init__(self, clsname: str = "", composed: bool = True):
        self.clsname = clsname
        self.composed = composed
        self.nest_level: int

        self.traits_gens: dict[str, TraitGenerator] = {}
        self.traits: dict[str, TraitType] = {}
        self.subschemes: dict[str, SchemeGenerator] = {}

    @classmethod
    def create(
        cls,
        clsname: str = "",
        composed: bool = True,
        nested=True,
        _nest_level: int = 0,
        **trait_kwargs,
    ) -> st.SearchStrategy["SchemeGenerator"]:
        @st.composite
        def strat_simple(draw: Drawer) -> "SchemeGenerator":
            gen = cls(clsname=clsname, composed=composed)
            gen.draw_traits(draw, **trait_kwargs)
            return gen

        @st.composite
        def strat_composed(draw: Drawer) -> "SchemeGenerator":
            gen = cls(clsname=clsname, composed=composed)
            gen.draw_traits(draw, **trait_kwargs)
            gen.draw_subschemes(draw, nest_level=_nest_level, **trait_kwargs)
            return gen

        if not nested or _nest_level >= cls.MAX_NEST_LEVEL:
            return strat_simple()
        return strat_composed()

    def draw_traits(self, draw: Drawer, **kwargs):
        traits_gens = draw(
            st.lists(
                st_trait_gen(composed=self.composed, **kwargs), max_size=self.MAX_TRAITS
            )
        )
        n_traits = len(traits_gens)
        names = draw(
            st.lists(varname_st, min_size=n_traits, max_size=n_traits, unique=True)
        )
        self.traits_gens = {name: gen for name, gen in zip(names, traits_gens)}
        self.traits = {
            name: gen.draw_instance(draw).tag(config=True)
            for name, gen in self.traits_gens.items()
        }

    def draw_subschemes(self, draw: Drawer, nest_level: int, **trait_kwargs):
        names = draw(
            st.lists(
                varname_st.filter(lambda n: n not in self.traits),
                min_size=0,
                max_size=self.MAX_SUBSCHEMES,
                unique=True,
            )
        )
        for sub_name in names:
            scheme_gen = draw(
                self.create(
                    sub_name,
                    composed=self.composed,
                    _nest_level=nest_level + 1,
                    **trait_kwargs,
                )
            )
            scheme_gen.nest_level = nest_level + 1
            self.subschemes[sub_name] = scheme_gen
            scheme_cls = scheme_gen.get_cls()
            self.traits[sub_name] = subscheme(scheme_cls)

    def get_cls(self) -> type[Scheme]:
        return type(self.clsname, (Scheme,), dict(self.traits))

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


def st_scheme_cls(**kwargs) -> st.SearchStrategy[type[Scheme]]:
    return SchemeGenerator.create(**kwargs).map(lambda g: g.get_cls())


def st_scheme_instance(**kwargs) -> st.SearchStrategy[Scheme]:
    @st.composite
    def strat(draw) -> Scheme:
        scheme_gen = draw(SchemeGenerator.create(**kwargs))
        cls = scheme_gen.get_cls()
        values = draw(scheme_gen.st_values())
        return cls.instanciate_recursively(values)

    return strat()


def st_scheme_instances(n: int = 2, **kwargs) -> st.SearchStrategy[tuple[Scheme, ...]]:
    @st.composite
    def strat(draw: Drawer) -> tuple[Scheme, ...]:
        scheme_gen = draw(SchemeGenerator.create(**kwargs))
        cls = scheme_gen.get_cls()
        instances = []
        for _ in range(n):
            values = draw(scheme_gen.st_values())
            inst = cls.instanciate_recursively(values)
            instances.append(inst)
        return tuple(instances)

    return strat()
