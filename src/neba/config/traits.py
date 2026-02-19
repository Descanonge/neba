"""New traits."""

import re
from typing import Any, TypeVar, cast

from traitlets.traitlets import Float, Int, List, TraitType, Unicode, Union

T = TypeVar("T")


class Range(List[T]):
    """Allow to specify a list of items using ranges.

    The string must match ``start:stop[:step]``. This will generate values between
    *start* and *stop*, spaced by *step*. The *stop* value will be included (if *step*
    allows it). *step* is optional and will default to one. The order of *start* and
    *stop* will dictate if values are ascending or descending.

    The trait type must be one of :attr:`allowed_traits` (by default float or int).

    ::

        "2000:2005": [2000, 2001, 2002, 2003, 2004, 2005]
        "2000:2005:2": [2000, 2002, 2004]
        "2005:2000:2": [2005, 2003, 2001]
        "0.:2.:0.5": [0.0, 0.5, 1.0, 1.5, 2.0]

    """

    range_max_len: int = 500
    range_rgx = re.compile("([-+.0-9eE]+?):([-+.0-9eE]+?)(?::([-+.0-9eE]*?))?")
    allowed_traits: list[type[TraitType]] = [Float, Int]
    """Allowed trait types."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self._trait is None or not isinstance(
            self._trait, tuple(self.allowed_traits)
        ):
            name = self.__class__.__name__
            received = self._trait.__class__.__name__
            raise TypeError(
                f"Trait type {received} is not allowed for {name}. "
                f"Must be one of {self.allowed_traits}"
            )

    def from_string(self, s: str) -> list[T] | None:
        """Get a value from a config string.

        Will test for a string specifying a range.
        """
        m = self.range_rgx.fullmatch(s)
        if m is not None:
            try:
                return self.generate_range(*m.groups(default="1"))
            except Exception as err:
                raise ValueError(f"Failed to parse range specification {s}") from err
        return super().from_string(s)

    def from_string_list(self, s_list: list[str]) -> list[T] | None:
        """Get a value from a config string.

        Will test for a string specifying a range.
        """
        values = []
        for s in s_list:
            m = self.range_rgx.fullmatch(s)
            if m is not None:
                try:
                    values += self.generate_range(*m.groups(default="1"))
                except Exception as err:
                    raise ValueError(
                        f"Failed to parse range specification {s}"
                    ) from err
            else:
                values.append(cast(T, self.item_from_string(s)))
        return values

    def generate_range(self, start_s: str, stop_s: str, step_s: str) -> list[T]:
        """Get a list of value from a range specification.

        Parameters
        ----------
        start_s, stop_s, step_s
            Strings parameters found in the range specification. Step cannot be ommited
            here and must be replaced by a default.
        """
        import operator as op

        args_str = dict(start=start_s, stop=stop_s, step=step_s)
        args = []
        for var, arg_str in args_str.items():
            arg = self._trait.from_string(arg_str)
            if arg is None:
                trait_cls = self._trait.__class__.__name__
                raise ValueError(f"Could not parse {var}={arg_str} into {trait_cls}")
            args.append(arg)

        start, stop, step = args

        if step == 0:
            raise IndexError("Step cannot be zero.")

        step = abs(step)
        descending = start > stop
        if descending:
            step = -step

        # stop when "value comp_op stop"
        comp_op = op.lt if descending else op.gt

        values = []
        current = start
        for _ in range(self.range_max_len):
            values.append(current)
            current += step
            if comp_op(current, stop):
                break

        if len(values) >= self.range_max_len:
            raise IndexError(
                f"Range length exceding maximum length ({self.range_max_len}). "
                "Possible mistake, else change FixableTrait.range_max_len"
            )

        return values


class Fixable(Union):
    """Fixable parameter, specified in a filename pattern.

    A fixable parameter meant to work with :mod:`filefinder`. It can take:

    1. a value of the appropriate type,
    2. a string specifying a range of values, see :class:`.RangeTrait`,
    3. a string that will be interpreted as a regular expression to match a filename
       part,
    4. a list of values (see 1), any of which will be accepted as a valid filename part.

    Parameters
    ----------
    trait
        Trait instance.
    default_value
        The default value.
    unicode
        Allow string values. Default is False as this can be dangerous, any value from
        command line that cannot be parsed would still be allowed.
    range
        If trait is Int or Float, allow to transform a string into a range of value
        using :class:`.RangeTrait`.
    allow_none
        Allow None as a valid value. Default is True.
    kwargs
        Arguments passed to the Union trait created.
    """

    info_text = "a fixable"

    def __init__(
        self,
        trait: TraitType,
        default_value: Any = None,
        unicode: bool = False,
        range: bool = True,
        allow_none: bool = True,
        **kwargs: Any,
    ) -> None:
        self.trait = trait

        # Create the types for Union
        traits = [trait]
        if range and isinstance(trait, tuple(Range.allowed_traits)):
            traits.append(Range(trait))
        else:
            traits.append(List(trait))
        if unicode and not isinstance(trait, Unicode):
            traits.append(Unicode())

        super().__init__(
            traits, default_value=default_value, allow_none=allow_none, **kwargs
        )
