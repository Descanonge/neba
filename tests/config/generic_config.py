"""Generic configuration to test.

Here we define a typical configuration with nested subsections, and with various traits
(simple and composed).

An accompanying class is defined and stores information statically about our generic
config.
"""

from typing import Any, Generic, TypeVar

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

from neba.config.section import Section, Subsection
from tests.utils import Drawer

from .trait_generation import DummyClass, trait_to_strat

S = TypeVar("S", bound=Section)


class SectionInfo(Generic[S]):
    """Class containing information about a given Section class.

    It retains the traits defined on this section level. For any trait, it can give its
    default value or generate a possible value.

    It is recursive for subsections. The list of keys is cached for efficiency (we use
    hypothesis so I fear that computing it dynamically might be costly).

    If the test modifies the section class (like when testing add_trait), use
    section_subclass and section_subclass_inst that will subclass the section and all
    its subsections. That way the original class is not modified.
    """

    section: type[S]
    subsections: dict[str, type["SectionInfo"]] = {}
    aliases: dict[str, type["SectionInfo"]] = {}

    traits: dict[str, TraitType] = {}

    cache: dict[tuple[bool, bool, bool], Any] = {}

    def __init_subclass__(cls):
        # Make copies
        cls.cache = {}
        cls.traits = dict(cls.traits)
        cls.subsections = dict(cls.subsections)
        cls.aliases = dict(cls.aliases)

    @classmethod
    def section_subclass(cls) -> type[S]:
        """Return subclass of section."""
        # we subclass all subsections

        def subclass(section_cls):
            section_subcls = type(section_cls.__name__, (section_cls,), {})
            for name, subsection_cls in section_subcls.class_subsections().items():
                section_subcls._subsections[name] = Subsection(subclass(subsection_cls))
            return section_subcls

        return subclass(cls.section)

    @classmethod
    def section_subclass_inst(cls, *args, **kwargs) -> S:
        """Return instance of a subclass of section."""
        return cls.section_subclass()(*args, **kwargs)

    @classmethod
    def keys(
        cls, subsections: bool = False, recursive: bool = True, aliases: bool = False
    ) -> list[str]:
        """Names of traits in this section and its subsections."""
        cache_key = (subsections, recursive, aliases)
        if (cache_out := cls.cache.get(cache_key, None)) is not None:
            return cache_out

        traits = list(cls.traits.keys())
        traits.sort()
        for name, sub_info in cls.subsections.items():
            if subsections:
                traits.append(name)
            if not recursive:
                continue
            traits += [
                f"{name}.{k}" for k in sub_info.keys(subsections, recursive, aliases)
            ]

        if aliases:
            for short, target in cls.aliases.items():
                if subsections:
                    traits.append(short)
                if not recursive:
                    continue
                traits += [
                    f"{short}.{k}" for k in target.keys(subsections, recursive, aliases)
                ]

        cls.cache[cache_key] = traits
        return traits

    @classmethod
    def default(cls, key: str) -> Any:
        """Get the default value of a key."""
        if key in cls.traits:
            trait = cls.traits[key]
            return trait.default()
        sub, *subkey = key.split(".")
        if sub in cls.aliases:
            subinfo = cls.aliases[sub]
        else:
            subinfo = cls.subsections[sub]
        return subinfo.default(".".join(subkey))

    @classmethod
    def generic_args(cls) -> dict[str, tuple[list[str], Any]]:
        """Return arguments as could be given on command-line and their parsed value."""
        raise NotImplementedError

    @classmethod
    def value_strat(cls, key: str) -> st.SearchStrategy:
        """Strategy to get value for a specific keys."""
        if key in cls.traits:
            trait = cls.traits[key]
            return trait_to_strat(trait)
        sub, *subkey = key.split(".")
        if sub in cls.aliases:
            subinfo = cls.aliases[sub]
        else:
            subinfo = cls.subsections[sub]
        return subinfo.value_strat(".".join(subkey))

    @classmethod
    def values_strat(cls, **kwargs) -> st.SearchStrategy[dict]:
        """Strategy of values for a random selection of keys."""

        @st.composite
        def strat(draw: Drawer, **kwargs) -> dict:
            keys = draw(st.lists(st.sampled_from(cls.keys(**kwargs))))
            return {key: draw(cls.value_strat(key)) for key in keys}

        return strat(**kwargs)

    @classmethod
    def values_strat_nested(cls, **kwargs) -> st.SearchStrategy[tuple[dict, dict]]:
        """Strategy of values for a random selection of keys (both flat and nested)."""

        @st.composite
        def strat(draw: Drawer, **kwargs) -> tuple[dict, dict]:
            keys = draw(st.lists(st.sampled_from(cls.keys(**kwargs))))
            out_nest: dict = {}
            out_flat: dict = {}
            for key in keys:
                value = draw(cls.value_strat(key))
                subout = out_nest
                keypath = key.split(".")
                for subkey in keypath[:-1]:
                    subout.setdefault(subkey, {})
                    subout = subout[subkey]
                subout[keypath[-1]] = value
                out_flat[key] = value
            return out_nest, out_flat

        return strat(**kwargs)

    @classmethod
    def values_half_strat(cls, **kwargs) -> st.SearchStrategy[dict]:
        """Strategy of values for half of keys."""

        @st.composite
        def strat(draw: Drawer, **kwargs) -> dict:
            out = {
                k: draw(cls.value_strat(k))
                for i, k in enumerate(cls.keys(**kwargs))
                if i % 2 == 0
            }
            return out

        return strat(**kwargs)

    @classmethod
    def values_all_strat(cls, **kwargs) -> st.SearchStrategy[dict]:
        """Strategy of values for all keys."""

        @st.composite
        def strat(draw: Drawer, **kwargs) -> dict:
            out = {k: draw(cls.value_strat(k)) for k in cls.keys(**kwargs)}
            return out

        return strat(**kwargs)


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
    inst = Instance(DummyClass, default_value=DummyClass(1), args=(), kw={})
    type = Type(klass=DummyClass)

    # Union
    union_num = Union([Int(), Float()], default_value=0.0)
    union_num_str = Union([Int(), Float(), Unicode()], default_value="0")
    union_list = Union([Int(), List(Int())], default_value=[0])

    # For alias testing, it must be dealt separately, it is not included in generic_args
    alias_only = Int(0)


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
        inst=Instance(DummyClass, default_value=DummyClass(1), args=(), kw={}),
        type=Type(klass=DummyClass),
        # Union
        union_num=Union([Int(), Float()], default_value=0.0),
        union_num_str=Union([Int(), Float(), Unicode()], default_value="0"),
        union_list=Union([Int(), List(Int())], default_value=[0]),
        # For alias testing, it won't superseed any other trait
        alias_only=Int(0),
    )

    @classmethod
    def generic_args(cls) -> dict[str, tuple[list[str], Any]]:
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
            type=(
                ["tests.config.trait_generation.DummySubclass"],
                "tests.config.trait_generation.DummySubclass",
            ),
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

    aliases = {
        "empty_short": "empty_b.empty_c",
        "deep_short": "deep_sub.sub_generic_deep",
    }

    sub_generic = Subsection(GenericSection)

    twin_a = Subsection(TwinSubsection)
    twin_b = Subsection(TwinSubsection)

    class sub_twin(Section):
        twin_c = Subsection(TwinSubsection)

    class deep_sub(Section):
        sub_generic_deep = Subsection(GenericSection)

    class empty_a(Section):
        pass

    class empty_b(Section):
        class empty_c(Section):
            pass


class SubTwinInfo(SectionInfo):
    section = GenericConfig._sub_twinSectionDef
    subsections = dict(twin_c=TwinSubsectionInfo)


class DeepSubInfo(SectionInfo):
    section = GenericConfig._deep_subSectionDef
    subsections = dict(sub_generic_deep=GenericSectionInfo)


class Empty_a_Info(SectionInfo):
    section = GenericConfig._empty_aSectionDef


class Empty_c_Info(SectionInfo):
    section = GenericConfig._empty_bSectionDef._empty_cSectionDef


class Empty_b_Info(SectionInfo):
    section = GenericConfig._empty_bSectionDef
    subsections = dict(empty_c=Empty_c_Info)


class GenericConfigInfo(GenericSectionInfo):
    section = GenericConfig
    subsections = dict(
        sub_generic=GenericSectionInfo,
        twin_a=TwinSubsectionInfo,
        twin_b=TwinSubsectionInfo,
        sub_twin=SubTwinInfo,
        deep_sub=DeepSubInfo,
        empty_a=Empty_a_Info,
        empty_b=Empty_b_Info,
    )

    aliases = {
        "empty_short": Empty_c_Info,
        "deep_short": GenericSectionInfo,
    }

    @classmethod
    def generic_args(cls) -> dict[str, tuple[list[str], Any]]:
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
