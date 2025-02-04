"""Generate Sections."""

import typing as t

import hypothesis.strategies as st
from traitlets import TraitType

from data_assistant.config.section import Section, subsection

from .trait_generation import TraitGenerator, st_trait_gen
from .util import Drawer, st_varname


class EmptySection(Section):
    pass


class SectionGenerator:
    """Generate a Section."""

    def __init__(
        self,
        clsname: str = "",
        traits_gens: dict[str, TraitGenerator] | None = None,
        subsections: dict[str, "SectionGenerator"] | None = None,
    ):
        self.clsname = clsname
        self.nest_level: int

        if traits_gens is None:
            traits_gens = {}
        if subsections is None:
            subsections = {}
        self.traits_gens: dict[str, TraitGenerator] = traits_gens
        self.subsections: dict[str, SectionGenerator] = subsections

        self.traits: dict[str, TraitType] = {}

    def get_cls(self) -> type[Section]:
        return type(self.clsname, (Section,), dict(self.traits))

    def draw_traits(self, draw: Drawer, **kwargs):
        self.traits = {
            name: gen.draw_instance(draw).tag(config=True)
            for name, gen in self.traits_gens.items()
        }

        for sub_gen in self.subsections.values():
            sub_gen.draw_traits(draw)

        for name, sub_gen in self.subsections.items():
            cls = sub_gen.get_cls()
            self.traits[name] = subsection(cls)

    def draw_instance(self, draw: Drawer) -> Section:
        self.draw_traits(draw)
        return self.get_cls()()

    def st_inst(self) -> st.SearchStrategy[Section]:
        @st.composite
        def strat(draw: Drawer) -> Section:
            return self.draw_instance(draw)

        return strat()

    def st_values_single(self) -> st.SearchStrategy[dict[str, t.Any]]:
        """Get mapping of values for every trait on this level."""

        @st.composite
        def strat(draw: Drawer) -> dict[str, t.Any]:
            values = {
                name: draw(gen.st_value())
                for name, gen in self.traits_gens.items()
                if name not in self.subsections
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
                for sub_name, sub_gen in gen.subsections.items():
                    values[sub_name] = recurse(sub_gen)
                return values

            return recurse(self)

        return strat()


def section_gen_to_cls(
    section_gen: SectionGenerator, **kwargs
) -> st.SearchStrategy[type[Section]]:
    @st.composite
    def strat(draw) -> type[Section]:
        section_gen.draw_traits(draw)
        cls = section_gen.get_cls()
        return cls

    return strat()


def section_st_to_cls(
    strat: st.SearchStrategy[SectionGenerator], **kwargs
) -> st.SearchStrategy[type[Section]]:
    @st.composite
    def out(draw: Drawer) -> type[Section]:
        gen = draw(strat)
        return draw(section_gen_to_cls(gen, **kwargs))

    return out()


def section_gen_to_instance(
    section_gen: SectionGenerator, **kwargs
) -> st.SearchStrategy[Section]:
    @st.composite
    def strat(draw) -> Section:
        section_gen.draw_traits(draw)
        cls = section_gen.get_cls()
        values = draw(section_gen.st_values())
        return cls(values)

    return strat()


def section_st_to_instance(
    strat: st.SearchStrategy[SectionGenerator], **kwargs
) -> st.SearchStrategy[Section]:
    @st.composite
    def out(draw: Drawer) -> Section:
        gen = draw(strat)
        return draw(section_gen_to_instance(gen, **kwargs))

    return out()


def section_gen_to_instances(
    section_gen: SectionGenerator, n: int = 2, **kwargs
) -> st.SearchStrategy[tuple[Section, ...]]:
    @st.composite
    def strat(draw: Drawer) -> tuple[Section, ...]:
        section_gen.draw_traits(draw)
        cls = section_gen.get_cls()
        instances = []
        for _ in range(n):
            values = draw(section_gen.st_values())
            inst = cls(values)
            instances.append(inst)
        return tuple(instances)

    return strat()


def section_st_to_instances(
    strat: st.SearchStrategy[SectionGenerator],
    n: int = 2,
    **kwargs,
) -> st.SearchStrategy[tuple[Section, ...]]:
    @st.composite
    def out(draw: Drawer) -> tuple[Section, ...]:
        gen = draw(strat)
        return draw(section_gen_to_instances(gen, **kwargs))

    return out()


def st_section_gen_single_trait(**kwargs) -> st.SearchStrategy[SectionGenerator]:
    @st.composite
    def strat(draw: Drawer) -> SectionGenerator:
        trait_gen = draw(st_trait_gen(**kwargs))
        name = draw(st_varname)
        return SectionGenerator("single", {name: trait_gen})

    return strat()
