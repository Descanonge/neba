"""Test various functions of data_assistant.config.util."""

import hypothesis.strategies as st
from hypothesis import given

from data_assistant.config.util import flatten_dict, get_trait_typehint, nest_dict

from ..util import st_varname


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
        return get_trait_typehint(x, **kwargs) == target

    def test_basic_object(self):
        assert self.valid(1, "int")
        assert self.valid()
        # any object
        # a string
        # a type
        pass

    def test_basic_trait(self):
        pass

    def test_simple_compound(self):
        pass

    def test_dict(self):
        pass

    def test_deep_nest(self):
        pass

    def test_stringify_too_long(self):
        pass
