"""Generate Sections."""

import typing as t

import hypothesis.strategies as st
from traitlets import TraitType

from neba.config.section import Section, Subsection
from tests.util import Drawer, st_varname

from .trait_generation import TraitGenerator, st_trait_gen


class SectionGenerator:
    """Generate a Section."""

    MAX_SIZE = 4
    traits: dict[str, TraitType]

    def __init__(
        self,
        clsname: str = "",
        traits_gens: dict[str, TraitGenerator] | None = None,
        subsections: dict[str, "SectionGenerator"] | None = None,
    ):
        self.clsname = clsname

        if traits_gens is None:
            traits_gens = {}
        if subsections is None:
            subsections = {}
        self.traits_gens: dict[str, TraitGenerator] = traits_gens
        self.subsections: dict[str, SectionGenerator] = subsections

    def draw_traits(self, draw: Drawer, **kwargs):
        self.traits = {
            name: gen.draw_instance(draw).tag(config=True)
            for name, gen in self.traits_gens.items()
        }

        for sub_gen in self.subsections.values():
            sub_gen.draw_traits(draw)

    def get_cls(self):
        classdict = self.traits.copy()
        for name, subgen in self.subsections.items():
            classdict[name] = Subsection(subgen.get_cls())
        return type(self.clsname, (Section,), classdict)

    def st_cls(self, **kwargs) -> st.SearchStrategy[type[Section]]:
        """Strategy for Section class."""

        @st.composite
        def strat(draw: Drawer, **kwargs) -> type[Section]:
            self.draw_traits(draw, **kwargs)
            return self.get_cls()

        return strat(**kwargs)

    def st_inst_default(self, **kwargs) -> st.SearchStrategy[Section]:
        """Strategy for Section instance, with the default values."""
        return self.st_cls(**kwargs).map(lambda cls: cls())

    def draw_values(self, draw: Drawer) -> dict:
        values = {name: draw(gen.st_value()) for name, gen in self.traits_gens.items()}
        for name, secgen in self.subsections.items():
            values_subsec = secgen.draw_values(draw)
            values |= {f"{name}.{k}": v for k, v in values_subsec.items()}

        return values

    def st_values(self) -> st.SearchStrategy[dict[str, t.Any]]:
        """Get flat mapping of values for every trait."""

        @st.composite
        def strat(draw: Drawer) -> dict[str, t.Any]:
            return self.draw_values(draw)

        return strat()


def st_section_generator(max_leaves=32) -> st.SearchStrategy[SectionGenerator]:
    base = st.dictionaries(
        keys=st_varname, values=st_trait_gen(), max_size=SectionGenerator.MAX_SIZE
    )

    def extend(
        base: st.SearchStrategy,
    ) -> st.SearchStrategy[dict[str, TraitGenerator | t.Any]]:
        return st.dictionaries(
            keys=st_varname, values=base, max_size=SectionGenerator.MAX_SIZE
        )

    @st.composite
    def strat(draw: Drawer):
        def recurse(
            gen_dict: dict[str, t.Any | TraitGenerator],
        ) -> tuple[dict[str, TraitGenerator], dict[str, SectionGenerator]]:
            traits = {}
            subsections = {}
            for k, v in gen_dict.items():
                if isinstance(v, dict):
                    subsections[k] = SectionGenerator(k + "__class", *recurse(v))
                else:
                    traits[k] = v
            return traits, subsections

        gen_dict = draw(st.recursive(base, extend, max_leaves=max_leaves))
        return SectionGenerator("", *recurse(gen_dict))

    return strat()


def st_section_class(
    st_gen: st.SearchStrategy[SectionGenerator] | None = None,
) -> st.SearchStrategy[type[Section]]:
    if st_gen is None:
        st_gen = st_section_generator()

    @st.composite
    def strat(draw: Drawer) -> type[Section]:
        gen = draw(st_gen)
        gen.draw_traits(draw)
        return gen.get_cls()

    return strat()


def st_section_inst(
    st_gen: st.SearchStrategy[SectionGenerator] | None = None,
    n_set=1,
) -> st.SearchStrategy[tuple[Section, ...]]:
    if st_gen is None:
        st_gen = st_section_generator()

    @st.composite
    def strat(draw: Drawer) -> tuple[Section, ...]:
        gen = draw(st_gen)
        gen.draw_traits(draw)
        cls = gen.get_cls()

        instances = []
        for _ in range(n_set):
            values = draw(gen.st_values())
            instances.append(cls(values))

        return tuple(instances)

    return strat()
