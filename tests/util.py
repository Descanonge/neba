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
    TraitType,
    Type,
    Unicode,
    Union,
)

from data_assistant.config import Scheme

SIMPLE_TRAIT_TYPES: list[type[TraitType]] = [Bool, Float, Int, Unicode]
COMPOSED_TRAIT_TYPES: list[type[TraitType]] = [Dict, Enum, Instance, List, Type, Union]


class TraitGenerator:
    """Generate a trait.

    Parameters
    ----------
    traittype
        Type of the trait to generate
    has_default
        Wether to draw a default value (true) or not. If left to None, its value will be
        picked at random by hypothesis.
    """

    def __init__(self, traittype: type[TraitType], has_default: bool | None, **kwargs):
        self.traittype = traittype
        self.has_default = has_default
        self.kwargs = kwargs

    def draw_instance(self, draw) -> TraitType:
        """Generate trait object.

        Pick a default value if :attr:`has_default` is True. If the attribute is None,
        draw its value (True or False, 50/50).
        """
        if self.has_default is None:
            self.has_default = draw(st.booleans())

        kwargs = dict(self.kwargs)
        if self.has_default:
            kwargs["default_value"] = draw(self.get_value_strategy())

        return self.traittype(**kwargs)

    def get_value_strategy(self, **kwargs) -> st.SearchStrategy:
        """Return a strategy to pick an appopriate value."""
        if issubclass(self.traittype, Bool):
            return st.booleans()
        if issubclass(self.traittype, Int):
            return st.integers(**kwargs)
        if issubclass(self.traittype, Float):
            kwargs = dict(allow_nan=False, allow_infinity=False) | kwargs
            return st.floats(**kwargs)
        if issubclass(self.traittype, Unicode):
            return st.text(max_size=32)
        raise TypeError(f"Unsupported trait type: {self.traittype}")


def st_trait_gen(
    composed: bool = False, has_default: bool | None = None
) -> st.SearchStrategy[TraitGenerator]:
    @st.composite
    def strat(draw) -> TraitGenerator:
        traitlist = SIMPLE_TRAIT_TYPES
        if composed:
            traitlist += COMPOSED_TRAIT_TYPES
        traittype = draw(st.sampled_from(traitlist))
        trait_gen = TraitGenerator(traittype, has_default=has_default)
        return trait_gen

    return strat()


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

    def __init__(self, composed: bool = False):
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
