"""Generic section to test.

Here we should define a typical section, with nested subsections defined via function
subsection or dynamically, with various traits (simple and composed).
It should be used for basic stuff that would not translate super well in hypothesis.
We can manipulate very clearly the trait, their values, if they are default or None.
We can have multiple instances that have different values.

We can keep track of some information as well such as the number of traits, subsections,
etc to have easy access to it.
"""

import typing as t

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

from data_assistant.config.section import Section, subsection

from .trait_generation import trait_to_strat
from .util import Drawer

S = t.TypeVar("S", bound=Section)


class SectionInfo(t.Generic[S]):
    """Class containing information about a given Section class.

    It retains the traits defined on this section level, and in all subsections. For any
    trait, it can give its default value or generate a possible value. It can list
    the names of traits.
    """

    # TODO add aliases

    section: type[S]
    subsections: dict[str, "SectionInfo"] = {}

    traits: dict[str, TraitType] = {}

    traits_this_level: list[str]
    """Names of traits in this section."""
    traits_total: list[str]
    """Names of traits in this section and its subsections."""
    keys_this_level: list[str]
    """Names of traits and subschemes for this section."""
    keys_total: list[str]
    """Names of all traits and subschemes."""

    def __init_subclass__(cls) -> None:
        # make copies to avoid interferences
        cls.traits = dict(cls.traits)
        cls.subsections = dict(cls.subsections)

        cls.traits_this_level = list(cls.traits.keys())
        cls.traits_this_level.sort()

        cls.keys_this_level = list(cls.traits_this_level)
        cls.traits_total = list(cls.traits_this_level)
        cls.keys_total = list(cls.traits_this_level)

        # recurse in subsections
        for name, sub_info in cls.subsections.items():
            # subsection is a key
            cls.keys_this_level.append(name)

            cls.traits_total += [f"{name}.{k}" for k in sub_info.traits_total]

            cls.keys_total.append(name)
            cls.keys_total += [f"{name}.{k}" for k in sub_info.keys_total]

    @classmethod
    def default(cls, key: str) -> t.Any:
        """Get the default value of a key."""
        if key in cls.traits:
            trait = cls.traits[key]
            return trait.default()
        sub, *subkey = key.split(".")
        return cls.subsections[sub].default(".".join(subkey))

    @classmethod
    def generic_args(cls) -> dict[str, tuple[list[str], t.Any]]:
        """Return arguments as could be given on command-line and their parsed value."""
        raise NotImplementedError

    @classmethod
    def value_strat(cls, key: str) -> st.SearchStrategy:
        """Strategy to get value for a specific keys."""
        if key in cls.traits:
            trait = cls.traits[key]
            return trait_to_strat(trait)
        sub, *subkey = key.split(".")
        return cls.subsections[sub].value_strat(".".join(subkey))

    @classmethod
    def values_strat(cls) -> st.SearchStrategy[dict]:
        """Strategy of values for a random selection of keys."""

        @st.composite
        def strat(draw: Drawer) -> dict:
            keys = draw(st.lists(st.sampled_from(cls.traits_total)))
            out = {k: draw(cls.value_strat(k)) for k in keys}
            return out

        return strat()

    @classmethod
    def values_half_strat(cls) -> st.SearchStrategy[dict]:
        """Strategy of values for half of keys."""

        @st.composite
        def strat(draw: Drawer) -> dict:
            out = {
                k: draw(cls.value_strat(k))
                for i, k in enumerate(cls.traits_total)
                if i % 2 == 0
            }
            return out

        return strat()

    @classmethod
    def values_all_strat(cls) -> st.SearchStrategy[dict]:
        """Strategy of values for all keys."""

        @st.composite
        def strat(draw: Drawer) -> dict:
            out = {k: draw(cls.value_strat(k)) for k in cls.traits_total}
            return out

        return strat()


class DummyClass:
    """Used for Instance and Type traits."""

    def __repr__(self):
        return f"{self.__class__.__name__}()"


dummy_instance = DummyClass()
DummySubclass = type("DummySubclass", (DummyClass,), {})
dummy_subinstance = DummySubclass()


class GenericSection(Section):
    """Generic section containing a wide selection of traits."""

    # Simple traits
    bool = Bool(True)
    float = Float(0.0)
    int = Int(0)
    str = Unicode("default")
    enum_int = Enum(values=[1, 2, 3], default_value=1)
    enum_str = Enum(values=["a", "b", "c"], default_value="a")
    enum_mix = Enum(values=[1, 2, 3, "a", "b", "c"], default_value=1)

    # Containers (list)
    list_int = List(Int(), default_value=[0])
    list_str = List(Unicode(), default_value=["a"])
    list_any = List(default_value=[0, "a"])
    list_nest = List(List(Int()), default_value=[[0, 2], [1, 3]])

    # Containers (set)
    set_int = Set(Int(), default_value=[0, 1, 2])
    set_any = Set(default_value=[0, 1, "a", "b"])
    set_union = Set(Union([Int(), Unicode()]), default_value=[0, 1, "a", "b"])

    # Containers (tuple)
    tuple_float = Tuple(Float(), Float(), default_value=(0.0, 1.0))
    tuple_mix = Tuple(Unicode(), Int(), Int(), default_value=("a", 0, 1))
    tuple_nest = Tuple(Int(), List(Int()), default_value=(0, [0, 1, 2]))

    # Containers (dict)
    dict_any = Dict(default_value={"a": 0, "b": 1})
    dict_str_int = Dict(
        value_trait=Int(), key_trait=Unicode(), default_value={"a": 0, "b": 1}
    )

    # Instance and Type
    inst = Instance(DummyClass, default_value=dummy_instance, args=(), kw={})
    type = Type(klass=DummyClass)

    # Union
    union_num = Union([Int(), Float()], default_value=0.0)
    union_num_str = Union([Int(), Float(), Unicode()], default_value="0")
    union_list = Union([Int(), List(Int())], default_value=[0])


class GenericSectionInfo(SectionInfo[GenericSection]):
    section = GenericSection
    subsections = {}

    traits = dict(
        bool=Bool(True),
        float=Float(0.0),
        int=Int(0),
        str=Unicode("default"),
        enum_int=Enum(values=[1, 2, 3], default_value=1),
        enum_str=Enum(values=["a", "b", "c"], default_value="a"),
        enum_mix=Enum(values=[1, 2, 3, "a", "b", "c"], default_value=1),
        # Containers (list)
        list_int=List(Int(), default_value=[0]),
        list_str=List(Unicode(), default_value=["a"]),
        list_any=List(default_value=[0, "a"]),
        list_nest=List(List(Int()), default_value=[[0, 2], [1, 3]]),
        # Containers (set)
        set_int=Set(Int(), default_value=[0, 1, 2]),
        set_any=Set(default_value=[0, 1, "a", "b"]),
        set_union=Set(Union([Int(), Unicode()]), default_value=[0, 1, "a", "b"]),
        # Containers (tuple)
        tuple_float=Tuple(Float(), Float(), default_value=(0.0, 1.0)),
        tuple_mix=Tuple(Unicode(), Int(), Int(), default_value=("a", 0, 1)),
        tuple_nest=Tuple(Int(), List(Int()), default_value=(0, [0, 1, 2])),
        # Containers (dict)
        dict_any=Dict(default_value={"a": 0, "b": 1}),
        dict_str_int=Dict(
            value_trait=Int(), key_trait=Unicode(), default_value={"a": 0, "b": 1}
        ),
        # Instance and Type
        inst=Instance(DummyClass, default_value=dummy_instance, args=(), kw={}),
        type=Type(klass=DummyClass),
        # Union
        union_num=Union([Int(), Float()], default_value=0.0),
        union_num_str=Union([Int(), Float(), Unicode()], default_value="0"),
        union_list=Union([Int(), List(Int())], default_value=[0]),
    )

    @classmethod
    def generic_args(cls) -> dict[str, tuple[list[str], t.Any]]:
        """Return arguments as could be given on command-line and their parsed value.

        Is also used as reference for creating manually configuration files.
        """
        generic_args = dict(
            bool=(["false"], False),
            float=(["1.0"], 1.0),
            int=(["1"], 1),
            str=(["value"], "value"),
            enum_int=(["2"], 2),
            enum_str=(["b"], "b"),
            enum_mix=(["2"], 2),
            # lists
            list_int=(["1", "2"], [1, 2]),
            list_str=(["b", "c"], ["b", "c"]),
            list_any=(["1", "b"], ["1", "b"]),
            # sets
            set_int=(["3", "4"], {3, 4}),
            set_any=(["1", "a", "c"], {"1", "a", "c"}),
            set_union=(["1", "a", "c"], {1, "a", "c"}),
            # tuple
            tuple_float=(["2", "3"], (2.0, 3.0)),
            tuple_mix=(["b", "2", "3"], ("b", 2, 3)),
            # dict
            dict_any=(["a=1", "b=2", "c=3"], dict(a="1", b="2", c="3")),
            dict_str_int=(["a=1"], dict(a=1)),
            # type (instance not parsable)
            type=(["tests.generic_sections.DummySubclass"], DummySubclass),
            # Union
            union_num=(["1"], 1),
            union_num_str=(["a"], "a"),
            union_list=(["1", "2"], [1, 2]),
        )
        return generic_args


class TwinSubsection(Section):
    int = Int(0)
    list_int = List(Int(), default_value=[0, 1])


class TwinSubsectionInfo(SectionInfo):
    section = TwinSubsection

    traits = dict(int=Int(0), list_int=List(Int(), default_value=[0, 1]))


class GenericConfig(GenericSection):
    """An example configuration with nested configuration."""

    sub_generic = subsection(GenericSection)

    twin_a = subsection(TwinSubsection)
    twin_b = subsection(TwinSubsection)

    class sub_twin(Section):
        twin_c = subsection(TwinSubsection)

    class deep_sub(Section):
        sub_generic_deep = subsection(GenericSection)

    class empty_a(Section):
        pass

    class empty_b(Section):
        class empty_c(Section):
            pass


class SubTwinInfo(SectionInfo):
    section = GenericConfig._sub_twinSectionDef  # type: ignore[attr-defined]
    subsections = dict(twin_c=TwinSubsectionInfo())


class DeepSubInfo(SectionInfo):
    section = GenericConfig._deep_subSectionDef  # type: ignore[attr-defined]
    subsections = dict(sub_generic_deep=GenericSectionInfo())


class Empty_a_Info(SectionInfo):
    section = GenericConfig._empty_aSectionDef  # type: ignore[attr-defined]


class Empty_c_Info(SectionInfo):
    section = GenericConfig._empty_bSectionDef._empty_cSectionDef  # type: ignore[attr-defined]


class Empty_b_Info(SectionInfo):
    section = GenericConfig._empty_bSectionDef  # type: ignore[attr-defined]
    subsections = dict(empty_c=Empty_c_Info())


class GenericConfigInfo(GenericSectionInfo):
    # TODO add aliases

    section = GenericConfig
    subsections = dict(
        sub_generic=GenericSectionInfo(),
        twin_a=TwinSubsectionInfo(),
        twin_b=TwinSubsectionInfo(),
        sub_twin=SubTwinInfo(),
        deep_sub=DeepSubInfo(),
        empty_a=Empty_a_Info(),
        empty_b=Empty_b_Info(),
    )

    @classmethod
    def generic_args(cls) -> dict[str, tuple[list[str], t.Any]]:
        generic_args = dict(super().generic_args())
        generic_args.update(
            {f"sub_generic.{k}": v for k, v in super().generic_args().items()}
        )
        generic_args.update(
            {
                f"deep_sub.sub_generic_deep.{k}": v
                for k, v in super().generic_args().items()
            }
        )
        return generic_args
