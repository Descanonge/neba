"""Test added traits."""

import math
import typing as t

import pytest
from data_assistant.config.util import RangeTrait
from hypothesis import example, given
from hypothesis import strategies as st
from traitlets import Bool, Float, Int, List


def test_range_trait_allowed_traits():
    RangeTrait(Int(1))
    RangeTrait(Int())
    RangeTrait(Float())


@pytest.mark.parametrize("input", [None, Bool(), List(), List(Int(1))])
def test_range_trait_wrong_input(input: t.Any):
    with pytest.raises(TypeError):
        if input is None:
            RangeTrait()
        else:
            RangeTrait(input)


@given(
    start=st.integers(),
    stop=st.integers(),
    step=st.one_of(st.none(), st.integers().filter(lambda i: i != 0)),
)
@example(0, 0, 1)
@example(0, 13, 4)
@example(13, 0, 4)
def test_range_trait_any_int(start: int, stop: int, step: int | None):
    input_string = f"{start}:{stop}"
    if step is None:
        step = 1
    else:
        input_string += f":{step}"

    trait: RangeTrait[int] = RangeTrait(Int())

    n_values = math.floor(abs(stop - start) / abs(step)) + 1
    if n_values >= trait.range_max_len:
        with pytest.raises(ValueError):
            trait.from_string(input_string)
        return

    values = trait.from_string(input_string)
    assert values is not None
    assert len(values) == n_values
    assert values[0] == start

    if abs(stop - start) % step == 0:
        assert values[-1] == stop

    if n_values > 1:
        assert abs(values[1] - values[0]) == abs(step)
