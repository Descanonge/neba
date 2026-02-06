"""Test added traits."""

import math
import typing as t

import pytest
from hypothesis import example, given, note
from hypothesis import strategies as st
from traitlets import Bool, Float, Int, List, TraitError

from neba.config.util import RangeTrait

floats_nice = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12
).map(lambda x: x if x > 1e-6 else 0.0)


class TestRangeTrait:
    def test_allowed_traits(self):
        RangeTrait(Int(1))
        RangeTrait(Int())
        RangeTrait(Float())

    @pytest.mark.parametrize("input", [None, Bool(), List(), List(Int(1))])
    def test_wrong_input(self, input: t.Any):
        with pytest.raises(TypeError):
            if input is None:
                RangeTrait()
            else:
                RangeTrait(input)

    def test_parsing(self):
        t = RangeTrait(Int())
        assert t.from_string("1:3") == [1, 2, 3]
        assert t.from_string("3:1") == [3, 2, 1]
        assert t.from_string("0:3:2") == [0, 2]
        assert t.from_string("3:0:2") == [3, 1]

        t = RangeTrait(Float())
        assert t.from_string("1:2:0.5") == [1.0, 1.5, 2.0]
        assert t.from_string("2:1:0.5") == [2.0, 1.5, 1.0]
        assert t.from_string("0:4:1.5") == [0.0, 1.5, 3.0]
        assert t.from_string("4:0:1.5") == [4.0, 2.5, 1.0]

        with pytest.raises(TraitError):
            t.from_string("wrong")
        with pytest.raises(TraitError):
            t.from_string("0:1:1:1")
        with pytest.raises(TraitError):
            t.from_string("0:a:1")
        with pytest.raises(ValueError):
            t.from_string("0:2:0")

    @given(
        start=st.integers(min_value=-20_000, max_value=20_000),
        stop=st.integers(min_value=-20_000, max_value=20_000),
        step=st.one_of(
            st.none(),
            st.integers(min_value=-1000, max_value=1000).filter(lambda i: i != 0),
        ),
    )
    @example(0, 0, 1)
    @example(0, 13, 4)
    @example(13, 0, 4)
    def test_any_int(self, start: int, stop: int, step: int | None):
        input_string = f"{start}:{stop}"
        if step is None:
            step = 1
        else:
            input_string += f":{step}"
        note(input_string)

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

    @given(
        start=floats_nice,
        stop=floats_nice,
        step=st.one_of(st.none(), floats_nice.filter(lambda x: abs(x) > 1e-4)),
    )
    @example(0, 0, 1)
    @example(0, 13, 4)
    @example(13, 0, 4)
    def test_any_float(self, start: float, stop: float, step: float | None):
        """Test range generation for floats.

        This reveals the logic of generate_range is quite simple and can be broken by
        floats. Large values of start/stop and small values of step can bring floating
        point approximations.
        I only test a more restricted span of values, that are more susceptible to be used
        in a configuration context (for list generation moreover). In clear: good enough.
        """
        input_string = f"{start}:{stop}"
        if step is None:
            step = 1
        else:
            input_string += f":{step}"
        note(input_string)

        trait: RangeTrait[float] = RangeTrait(Float())

        n_values = math.floor(abs(stop - start) / abs(step)) + 1
        if n_values >= trait.range_max_len:
            with pytest.raises(ValueError):
                trait.from_string(input_string)
            return

        values = trait.from_string(input_string)
        assert values is not None
        assert len(values) == n_values
        assert math.isclose(values[0], start)

        if not math.isclose(values[-1], stop):
            assert abs(values[-1] - stop) < abs(step)

        if n_values > 1:
            assert math.isclose(abs(values[1] - values[0]), abs(step))
