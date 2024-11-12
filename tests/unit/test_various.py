"""Test various functions of data_assistant.config.util."""

import hypothesis.strategies as st
from hypothesis import given
from traitlets import Dict, Enum, Instance, Int, List, Tuple, Type, Unicode, Union

from data_assistant.config.util import flatten_dict, get_trait_typehint, nest_dict
from tests.util import st_varname


class TestNest2Flat:
    single_level_flat = dict(a=0, b=1, c=2)

    two_levels_flat = {
        "a": 0,
        "b": 1,
        "c.a": 10,
        "c.b": 11,
        "c.c": 12,
        "c.d": 13,
        "e.a": 20,
        "e.g": 21,
    }
    two_levels_nested = dict(
        a=0, b=1, c=dict(a=10, b=11, c=12, d=13), e=dict(a=20, g=21)
    )

    deep_flat = {"a.b.c.d.e1": 0, "a.b.c.d.e2": 1}
    deep_nested = {"a": {"b": {"c": {"d": {"e1": 0, "e2": 1}}}}}

    def test_nest_dict(self):
        assert nest_dict({}) == {}
        assert nest_dict(self.single_level_flat) == self.single_level_flat
        assert nest_dict(self.two_levels_flat) == self.two_levels_nested
        assert nest_dict(self.deep_flat) == self.deep_nested

    def test_flatten_dict(self):
        assert flatten_dict({}) == {}
        assert flatten_dict(self.single_level_flat) == self.single_level_flat
        assert flatten_dict(self.two_levels_nested) == self.two_levels_flat
        assert flatten_dict(self.deep_nested) == self.deep_flat

    @given(
        nest=st.recursive(
            st.dictionaries(st_varname, st.just(0)),
            lambda children: st.dictionaries(st_varname, children),
        )
    )
    def test_nest_to_flat_around(self, nest: dict):
        flat = flatten_dict(nest)
        assert nest == nest_dict(flat)


class TestTypehint:
    """Test the string representation of trait types."""

    def valid(self, x, target: str, **kwargs):
        assert get_trait_typehint(x, **kwargs) == target

    def test_basic_object(self):
        self.valid(1, "~builtins.int")
        self.valid(1, "builtins.int", mode="full")
        self.valid(1, "int", mode="minimal")
        self.valid(dict(), "~builtins.dict")

        class Test:
            pass

        self.valid(Test(), "~tests.unit.test_various.Test")
        self.valid(Test(), "tests.unit.test_various.Test", mode="full")
        self.valid(Test(), "Test", mode="minimal")

        self.valid(Test, "~tests.unit.test_various.Test")
        self.valid(Test, "tests.unit.test_various.Test", mode="full")
        self.valid(Test, "Test", mode="minimal")

    def test_basic_trait(self):
        self.valid(Int(), "~traitlets.traitlets.Int")
        self.valid(Int(), "traitlets.traitlets.Int", mode="full")
        self.valid(Int(), "Int", mode="minimal")

        self.valid(Unicode(), "~traitlets.traitlets.Unicode")
        self.valid(Unicode(), "traitlets.traitlets.Unicode", mode="full")
        self.valid(Unicode(), "Unicode", mode="minimal")

        self.valid(Enum([1, 2]), "~traitlets.traitlets.Enum")
        self.valid(Enum([1, 2]), "traitlets.traitlets.Enum", mode="full")
        self.valid(Enum([1, 2]), "Enum", mode="minimal")

    def test_allow_none(self):
        self.valid(Int(allow_none=True), "~traitlets.traitlets.Int | None")
        self.valid(Int(allow_none=True), "traitlets.traitlets.Int | None", mode="full")
        self.valid(Int(allow_none=True), "Int | None", mode="minimal")

    def test_list(self):
        self.valid(List(), "~traitlets.traitlets.List")
        self.valid(List(), "traitlets.traitlets.List", mode="full")
        self.valid(List(), "List", mode="minimal")

        self.valid(List(Int()), "~traitlets.traitlets.List[~traitlets.traitlets.Int]")
        self.valid(
            List(Int()),
            "traitlets.traitlets.List[traitlets.traitlets.Int]",
            mode="full",
        )
        self.valid(List(Int()), "List[Int]", mode="minimal")

    def test_tuple(self):
        # simple
        trait = Tuple(Int(), Int(), Unicode())
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Tuple[~traitlets.traitlets.Int, "
                "~traitlets.traitlets.Int, ~traitlets.traitlets.Unicode]"
            ),
        )
        self.valid(trait, "Tuple[Int, Int, Unicode]", mode="minimal")

        # no trait specified
        self.valid(Tuple(), "~traitlets.traitlets.Tuple")
        self.valid(Tuple(), "Tuple", mode="minimal")

        # Recursive
        trait = Tuple(
            Tuple(Int(allow_none=True)), List(Unicode(), allow_none=True), Unicode()
        )
        self.valid(
            trait,
            "~traitlets.traitlets.Tuple["
            "~traitlets.traitlets.Tuple[~traitlets.traitlets.Int | None], "
            "~traitlets.traitlets.List[~traitlets.traitlets.Unicode] | None, "
            "~traitlets.traitlets.Unicode]",
        )
        self.valid(
            trait,
            "Tuple[Tuple[Int | None], List[Unicode] | None, Unicode]",
            mode="minimal",
        )

    def test_dict(self):
        # Both specified
        trait = Dict(key_trait=Unicode(), value_trait=Int(allow_none=True))
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Dict"
                "[~traitlets.traitlets.Unicode, ~traitlets.traitlets.Int | None]"
            ),
        )
        self.valid(trait, "Dict[Unicode, Int | None]", mode="minimal")

        # Only key specified
        trait = Dict(key_trait=Unicode())
        self.valid(trait, "~traitlets.traitlets.Dict[~traitlets.traitlets.Unicode]")
        self.valid(trait, "Dict[Unicode]", mode="minimal")

        # Only value specified
        trait = Dict(value_trait=Int(allow_none=True))
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Dict"
                "[~typing.Any, ~traitlets.traitlets.Int | None]"
            ),
        )
        self.valid(trait, "Dict[Any, Int | None]", mode="minimal")

        # None specified
        self.valid(Dict(), "~traitlets.traitlets.Dict")
        self.valid(Dict(), "Dict", mode="minimal")

    def test_instance_and_type(self):
        class Test:
            pass

        trait = Instance(Test)
        self.valid(
            trait, "~traitlets.traitlets.Instance[~tests.unit.test_various.Test]"
        )
        self.valid(trait, "Instance[Test]", mode="minimal")

        self.valid(Type(), "~traitlets.traitlets.Type")
        trait = Type(klass=Test)
        self.valid(trait, "~traitlets.traitlets.Type[~tests.unit.test_various.Test]")
        self.valid(trait, "Type[Test]", mode="minimal")

        # Str klass
        trait = Instance("some.Class")
        self.valid(trait, "~traitlets.traitlets.Instance[~some.Class]")
        self.valid(trait, "traitlets.traitlets.Instance[some.Class]", mode="full")
        self.valid(trait, "Instance[Class]", mode="minimal")
        trait = Type(klass="some.Class")
        self.valid(trait, "~traitlets.traitlets.Type[~some.Class]")
        self.valid(trait, "traitlets.traitlets.Type[some.Class]", mode="full")
        self.valid(trait, "Type[Class]", mode="minimal")

    def test_union(self):
        # 2 elements
        trait = Union([Int(), Unicode()])
        self.valid(trait, "~traitlets.traitlets.Int | ~traitlets.traitlets.Unicode")
        self.valid(trait, "Int | Unicode", mode="minimal")

        # 3 elements
        trait = Union([Int(), Unicode(), List(Int())])
        self.valid(
            trait,
            (
                "~traitlets.traitlets.Int | ~traitlets.traitlets.Unicode | "
                "~traitlets.traitlets.List[~traitlets.traitlets.Int]"
            ),
        )
        self.valid(trait, "Int | Unicode | List[Int]", mode="minimal")

    def test_union_allow_none(self):
        kw = dict(target="Int | Unicode | None", mode="minimal")
        self.valid(Union([Int(allow_none=True), Unicode()]), **kw)
        self.valid(Union([Int(), Unicode(allow_none=True)]), **kw)
        self.valid(Union([Int(allow_none=True), Unicode(allow_none=True)]), **kw)
        self.valid(Union([Int(allow_none=True), Unicode()], allow_none=True), **kw)

    def test_deep_nest(self):
        assert 0

    def test_stringify_too_long(self):
        assert 0
