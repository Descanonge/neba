"""Generate Schemes."""

import typing as t

import hypothesis.strategies as st
from traitlets import TraitType

from data_assistant.config.scheme import Scheme, subscheme

from .trait_generation import TraitGenerator, st_trait_gen
from .util import Drawer, st_varname


class EmptyScheme(Scheme):
    pass


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
                name: draw(gen.st_value())
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


def scheme_gen_to_cls(
    scheme_gen: SchemeGenerator, **kwargs
) -> st.SearchStrategy[type[Scheme]]:
    @st.composite
    def strat(draw) -> type[Scheme]:
        scheme_gen.draw_traits(draw)
        cls = scheme_gen.get_cls()
        return cls

    return strat()


def scheme_st_to_cls(
    strat: st.SearchStrategy[SchemeGenerator], **kwargs
) -> st.SearchStrategy[type[Scheme]]:
    @st.composite
    def out(draw: Drawer) -> type[Scheme]:
        gen = draw(strat)
        return draw(scheme_gen_to_cls(gen, **kwargs))

    return out()


def scheme_gen_to_instance(
    scheme_gen: SchemeGenerator, **kwargs
) -> st.SearchStrategy[Scheme]:
    @st.composite
    def strat(draw) -> Scheme:
        scheme_gen.draw_traits(draw)
        cls = scheme_gen.get_cls()
        values = draw(scheme_gen.st_values())
        return cls.instanciate_recursively(values)

    return strat()


def scheme_st_to_instance(
    strat: st.SearchStrategy[SchemeGenerator], **kwargs
) -> st.SearchStrategy[Scheme]:
    @st.composite
    def out(draw: Drawer) -> Scheme:
        gen = draw(strat)
        return draw(scheme_gen_to_instance(gen, **kwargs))

    return out()


def scheme_gen_to_instances(
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


def scheme_st_to_instances(
    strat: st.SearchStrategy[SchemeGenerator],
    n: int = 2,
    **kwargs,
) -> st.SearchStrategy[tuple[Scheme, ...]]:
    @st.composite
    def out(draw: Drawer) -> tuple[Scheme, ...]:
        gen = draw(strat)
        return draw(scheme_gen_to_instances(gen, **kwargs))

    return out()


def st_scheme_gen_single_trait(**kwargs) -> st.SearchStrategy[SchemeGenerator]:
    @st.composite
    def strat(draw: Drawer) -> SchemeGenerator:
        trait_gen = draw(st_trait_gen(**kwargs))
        name = draw(st_varname)
        return SchemeGenerator("single", {name: trait_gen})

    return strat()


class TypicalScheme(Scheme):
    pass


"""Here we should define a typical scheme, with nested subschemes defined via function
subscheme or dynamically, with various traits (simple and composed).
it should be used for basic stuff that would not translate super well in hypothesis.
we can manipulate very clearly the trait, their values, if they are default or None.

we can have multiple instances that have different values. (we should also check before
hand that different instances don't interfere with each other this is super important,
how ?)

We can keep track of some information as well such as the number of traits, subschemes,
etc to have easy access to it. Maybe it's not its place but another module that defines
a series of peculiar schemes ? Meh, I was thinking deeply nested subschemes but is that
THAT important ? It can be the subject of one or two tests that define themselves the
whole scheme.

it should contain twin subschemes that we keep knowledge of. ie subschemes (on the same
level and on different nesting level) that are different instances of the same subscheme
class. Keep the the path of each trait and its siblings.
"""
