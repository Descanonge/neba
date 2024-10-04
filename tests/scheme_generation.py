"""Generate Schemes."""

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

from data_assistant.config.scheme import Scheme, subscheme

from .trait_generation import TraitGenerator, st_trait_gen, trait_to_strat
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


class ClassDummy:
    pass


class_dummy = ClassDummy()


class GenericTraits(Scheme):
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
    inst = Instance(ClassDummy, default_value=class_dummy, args=(), kw={})
    type = Type(klass=ClassDummy)

    # Union
    union_num = Union([Int(), Float()], default_value=0.0)
    union_num_str = Union([Int(), Float(), Unicode()], default_value="0")
    union_list = Union([Int(), List(Int())], default_value=[0])


S = t.TypeVar("S", bound=Scheme)


class SchemeInfo(t.Generic[S]):
    scheme: type[S]
    subschemes: dict[str, "SchemeInfo"] = {}

    traits: dict[str, TraitType] = {}

    traits_this_level: list[str]
    traits_total: list[str]
    keys_this_level: list[str]
    keys_total: list[str]

    def __init_subclass__(cls) -> None:
        # make copies to avoid interferences
        cls.traits = dict(cls.traits)
        cls.subschemes = dict(cls.subschemes)

        cls.traits_this_level = list(cls.traits.keys())
        cls.traits_this_level.sort()

        cls.keys_this_level = list(cls.traits_this_level)
        cls.traits_total = list(cls.traits_this_level)
        cls.keys_total = list(cls.traits_this_level)

        # recurse in subschemes
        for name, sub_info in cls.subschemes.items():
            # subscheme is a key
            cls.keys_this_level.append(name)

            cls.traits_total += [f"{name}.{k}" for k in sub_info.traits_total]

            cls.keys_total.append(name)
            cls.keys_total += [f"{name}.{k}" for k in sub_info.keys_total]

    @classmethod
    def default(cls, key: str) -> t.Any:
        if key in cls.traits:
            trait = cls.traits[key]
            return trait.default()
        sub, *subkey = key.split(".")
        return cls.subschemes[sub].default(".".join(subkey))

    @classmethod
    def value_strat(cls, key: str) -> st.SearchStrategy:
        if key in cls.traits:
            trait = cls.traits[key]
            return trait_to_strat(trait)
        sub, *subkey = key.split(".")
        return cls.subschemes[sub].value_strat(".".join(subkey))

    @classmethod
    def values_strat(cls) -> st.SearchStrategy[dict]:
        @st.composite
        def strat(draw: Drawer) -> dict:
            keys = draw(st.lists(st.sampled_from(cls.traits_total)))
            out = {k: draw(cls.value_strat(k)) for k in keys}
            return out

        return strat()


class GenericTraitsInfo(SchemeInfo[GenericTraits]):
    scheme = GenericTraits
    subschemes = {}

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
        inst=Instance(ClassDummy, default_value=class_dummy, args=(), kw={}),
        type=Type(klass=ClassDummy),
        # Union
        union_num=Union([Float(), Int()], default_value=0.0),
        union_num_str=Union([Float(), Int(), Unicode()], default_value="0"),
        union_list=Union([Int(), List(Int())], default_value=[0]),
    )


class TwinSubscheme(Scheme):
    int = Int(0)
    list_int = List(Int(), default_value=[0, 1])


class TwinSubschemeInfo(SchemeInfo):
    scheme = TwinSubscheme

    traits = dict(int=Int(0), list_int=List(Int(), default_value=[0, 1]))


class GenericScheme(GenericTraits):
    sub_generic = subscheme(GenericTraits)

    twin_a = subscheme(TwinSubscheme)
    twin_b = subscheme(TwinSubscheme)

    class sub_twin(Scheme):
        twin_c = subscheme(TwinSubscheme)

    class deep_sub(Scheme):
        sub_generic_deep = subscheme(GenericTraits)

    class empty_a(Scheme):
        pass

    class empty_b(Scheme):
        class empty_c(Scheme):
            pass


class SubTwinInfo(SchemeInfo):
    scheme = GenericScheme._sub_twinSchemeDef  # type: ignore[attr-defined]
    subschemes = dict(twin_c=TwinSubschemeInfo())


class DeepSubInfo(SchemeInfo):
    scheme = GenericScheme._deep_subSchemeDef  # type: ignore[attr-defined]
    subschemes = dict(sub_generic_deep=GenericTraitsInfo())


class Empty_a_Info(SchemeInfo):
    scheme = GenericScheme._empty_aSchemeDef  # type: ignore[attr-defined]


class Empty_c_Info(SchemeInfo):
    scheme = GenericScheme._empty_bSchemeDef._empty_cSchemeDef  # type: ignore[attr-defined]


class Empty_b_Info(SchemeInfo):
    scheme = GenericScheme._empty_bSchemeDef  # type: ignore[attr-defined]
    subschemes = dict(empty_c=Empty_c_Info())


class GenericSchemeInfo(GenericTraitsInfo):
    scheme = GenericScheme
    subschemes = dict(
        sub_generic=GenericTraitsInfo(),
        twin_a=TwinSubschemeInfo(),
        twin_b=TwinSubschemeInfo(),
        sub_twin=SubTwinInfo(),
        deep_sub=DeepSubInfo(),
        empty_a=Empty_a_Info(),
        empty_b=Empty_b_Info(),
    )


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
