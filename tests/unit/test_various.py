"""Test various functions of data_assistant.config.util."""

import hypothesis.strategies as st
from hypothesis import given

from data_assistant.config.util import flatten_dict, nest_dict

from ..util import st_varname


def test_nest_dict():
    pass


def test_flatten_dict():
    pass


@given(
    nest=st.recursive(
        st.dictionaries(st_varname, st.just(0)),
        lambda children: st.dictionaries(st_varname, children),
    )
)
def test_nest_to_flat_around(nest: dict):
    flat = flatten_dict(nest)
    assert nest == nest_dict(flat)


class TestTypehint:
    """Test the string representation of trait types."""

    def test_stringify(self):
        # any object
        # a string
        # a type
        pass

    def test_stringify_too_long(self):
        pass

    def test_typehing(self):
        pass
