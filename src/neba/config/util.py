"""Various utilities."""

from __future__ import annotations

import re
import typing as t
from collections import abc

import Levenshtein
from traitlets.config import Configurable
from traitlets.traitlets import (
    Container,
    Dict,
    Float,
    Instance,
    Int,
    List,
    TraitType,
    Tuple,
    Type,
    Unicode,
    Union,
)
from traitlets.utils.text import wrap_paragraphs

from neba.util import get_classname


class ConfigError(Exception):
    """General exception for config loading."""


class UnknownConfigKeyError(ConfigError):
    """Key path does not lead to any known trait."""


class ConfigParsingError(ConfigError):
    """Unable to parse a config value."""


class MultipleConfigKeyError(ConfigError):
    """A parameter was specified more than once."""

    def __init__(
        self, key: str, values: abc.Sequence[t.Any], msg: str | None = None
    ) -> None:
        super().__init__()

        if msg is None:
            msg = (
                f"Configuration key '{key}' was specified more than once "
                f"with values {values}"
            )

        self.message = msg
        self.key = key
        self.values = values


T = t.TypeVar("T")


class RangeTrait(List[T]):
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

    def __init__(self, *args, **kwargs) -> None:
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
                values.append(t.cast(T, self.item_from_string(s)))
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


class FixableTrait(Union):
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
        default_value: t.Any = None,
        unicode: bool = False,
        range: bool = True,
        allow_none: bool = True,
        **kwargs,
    ) -> None:
        self.trait = trait

        # Create the types for Union
        traits = [trait]
        if range and isinstance(trait, tuple(RangeTrait.allowed_traits)):
            traits.append(RangeTrait(trait))
        else:
            traits.append(List(trait))
        if unicode and not isinstance(trait, Unicode):
            traits.append(Unicode())

        super().__init__(
            traits, default_value=default_value, allow_none=allow_none, **kwargs
        )


def tag_all_traits(**metadata) -> abc.Callable:
    """Tag all class-own traits.

    Do not replace existing tags.

    Parameters
    ----------
    metadata:
        Are passed to ``trait.tag(**metadata)``.
    """

    def decorator(cls: type[Configurable]):
        for trait in cls.class_own_traits().values():
            for key, value in metadata.items():
                if key not in trait.metadata:
                    trait.tag(**{key: value})
        return cls

    return decorator


def did_you_mean(suggestions: abc.Iterable[str], wrong_key: str) -> str | None:
    """Return element of `suggestions` closest to `wrong_key`."""
    min_distance = 9999
    closest_key = None
    for suggestion in suggestions:
        distance = Levenshtein.distance(suggestion, wrong_key)
        if distance < min_distance:
            min_distance = distance
            closest_key = suggestion

    return closest_key


def add_spacer(lines: list[str]) -> list[str]:
    """Add empty line if line above not already empty."""
    if lines[-1]:
        lines.append("")
    return lines


def underline(lines: list[str], char: str = "=") -> list[str]:
    """Underline content of the last line."""
    lines.append(char * len(lines[-1]))
    return lines


def indent(lines: list[str], num: int = 4, initial_indent: bool = True) -> list[str]:
    """Indent lines.

    Parameters
    ----------
    num
        Number of spaces to indent.
    initial_indent
        If False do not indent the first line.
    """
    for i, line in enumerate(lines):
        if i == 0 and not initial_indent:
            continue
        lines[i] = " " * num + line
    return lines


def wrap_text(text: str) -> list[str]:
    """Wrap text with multiple paragraph."""
    paragraphs = "\n\n".join(wrap_paragraphs(text))
    return paragraphs.splitlines()


def stringify(obj, rst=True) -> str:
    """Return a string representation of object.

    To put in trait metadata in the documentation.

    Parameters
    ----------
    rst
        If True, wrap the output in wrap the output in double backticks and link
        classes using roles.
    """

    def output(text: str) -> str:
        if rst:
            return f"``{text}``"
        return text

    if isinstance(obj, str):
        # Add ""s to be clear (especially when we have an empty string)
        return output(f'"{obj}"')

    # Try to have a nice link for types/classes
    if isinstance(obj, type):
        try:
            fullname = get_classname(obj)
        except AttributeError:
            fullname = str(obj)
        if rst:
            return f":class:`{fullname}`"
        return fullname

    out = str(obj)

    # arbitrary length of characters
    maxlength = 32
    if len(out) > maxlength:
        # the repr/str is too long
        out = out[:maxlength] + "..."

    return output(out)


def get_trait_typehint(
    trait: t.Any, mode: str = "short", aliases: abc.Mapping[str, str] | None = None
) -> str:
    """Return the typehint corresponding to a trait object.

    Parameters
    ----------
    trait:
        Trait instance. Also accept any other type of object.
    mode:
        If "short", add a ~ in front of the full typehint to only print the type name
        but still have a link. If minimal, only keep the name. If anything else, return
        the fully qualified link.
    """
    if aliases is None:
        aliases = {}

    def link(fullname: str) -> str:
        # if short we add tilde
        if mode == "short":
            return f"~{fullname}"
        # if minimal only keep the name
        if mode == "minimal":
            return fullname.split(".")[-1]

        return fullname

    def recurse(obj):
        """Recurse this function, keeping optional arguments."""
        return get_trait_typehint(obj, mode, aliases)

    def output(typehint, add_none=False):
        """Hook before returning the typehint."""  # noqa: D401
        if (alias := aliases.get(typehint.lstrip("~"), None)) is not None:
            typehint = alias
        if trait.allow_none or add_none:
            typehint += " | None"
        return typehint

    # Get the typehint of the trait itself
    typehint = link(get_classname(trait))

    # If simply an object, nothing specific to do:
    if not isinstance(trait, TraitType):
        return typehint

    if isinstance(trait, Union):
        subhints = [recurse(subtrait) for subtrait in trait.trait_types]
        any_none = any(subtrait.allow_none for subtrait in trait.trait_types)
        if any_none:
            subhints = [s.removesuffix(" | None") for s in subhints]
        interior = " | ".join(subhints)
        return output(interior, add_none=any_none)

    # Dict can have either its keys or values TraitType defined (or both).
    # If missing, automatically set to Any, which we ignore in typehint.
    # Except if value is defined, then we print Dict[Any, SomeType]
    if isinstance(trait, Dict):
        key_val = [""]
        has_key = trait._key_trait is not None
        has_val = trait._value_trait is not None

        if has_key:
            key_val[0] = recurse(trait._key_trait)
        if has_val:
            key_val.append(recurse(trait._value_trait))
            if not has_key:
                key_val[0] = link(get_classname(t.Any))

        if any(key_val):
            interior = f"[{', '.join(key_val)}]"
        else:
            interior = ""

        return output(f"{typehint}{interior}")

    # Tuple might have any number of traits defined from 0 (Any, not printed)
    if isinstance(trait, Tuple):
        interior = ", ".join(recurse(t) for t in trait._traits)
        if interior:
            interior = f"[{interior}]"
        return output(f"{typehint}{interior}")

    # List and Set
    if isinstance(trait, Container):
        if trait._trait is not None:
            interior = f"[{recurse(trait._trait)}]"
        else:
            interior = ""

        return output(f"{typehint}{interior}")

    if isinstance(trait, Type | Instance):
        if trait.klass is object:
            return output(typehint)
        if isinstance(trait.klass, str):
            interior = link(trait.klass)
        else:
            interior = recurse(trait.klass)
        return output(f"{typehint}[{interior}]")

    return output(typehint)
