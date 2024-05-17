"""Various utilities."""
from __future__ import annotations

import logging
import re
import typing as t
from collections import abc

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

if t.TYPE_CHECKING:
    from .application import ApplicationBase


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


class ConfigErrorHandler:
    """Context for handling configuration errors.

    This context uses the :attr:`~.application.ApplicationBase.strict_parsing` attribute
    to determine if any :class:`ConfigError` exception raised in the context should be
    silenced or not. If silenced, the error is still logged at the :attr:`log_level`
    (warning by default).

    Parameters
    ----------
    app
        The application object.
    key
        Eventually, the configuration key that is concerned. Used to make a more
        informative log message.

    """

    log_level: int = logging.WARNING
    """Level at which to log a silenced exception."""

    def __init__(self, app: ApplicationBase, key: str | None = None) -> None:
        self.app = app
        self.key = key

    def __enter__(self) -> t.Self:
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # No error
        if exc_type is None:
            return True

        # if not a ConfigError raise it
        if not issubclass(exc_type, ConfigError):
            return False

        # if strict parsing raise it
        if self.is_raise(exc_value):
            return False

        # else log error and resume
        self.log_exc(exc_value)
        return True

    def is_raise(self, exc: Exception) -> bool:
        """Return whether to raise or not.

        By default only use :attr:`~.application.ApplicationBase.strict_parsing`.
        """
        return self.app.strict_parsing

    def log_exc(self, exc: Exception) -> None:
        """Log message of the encountered exception."""
        log = getattr(self.app, "log", logging.getLogger(__name__))
        if self.key is None:
            args = ["Exception encountered in configuration"]
        else:
            args = ["Exception encountered for configuration key '%s'", self.key]
        log.log(self.log_level, *args, exc_info=exc)


T = t.TypeVar("T")


class RangeTrait(List[T]):
    """Allow to specify a list of items using ranges.

    The string must match is ``start:stop[:step]``. This will generate values between
    'start' and 'stop' spaced by 'step'. The 'stop' value will be included (``values <=
    stop``). The step is optional and will by default be one. It also does not need to
    be signed, only its absolute value will be used. The trait type must be one of
    :attr:`allowed_traits` (by default float or int). Here are some examples:

        "2000:2005": [2000, 2001, 2002, 2003, 2004, 2005]
        "2000:2005:2": [2000, 2002, 2004]
        "2005:2000:2": [2005, 2003, 2001]
        "0.:2.:0.5": [0.0, 0.5, 1.0, 1.5, 2.0]

    """

    range_max_len: int = 500
    range_rgx = re.compile("([-+.0-9eE]+?):([-+.0-9eE]+?)(?::([-+.0-9eE]*?))?")
    allowed_traits: list[type[TraitType]] = [Float, Int]

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

    A fixable parameter (ie specified in a filename pattern) can take:

    1. a value of the appropriate type (int, float, bool, or str depending on the format),
    2. a string that will be interpreted as a regular expression to match a filename
       part or a string specifying a range of values (see below).
    3. a list of values (see 1), any of which will be accepted as a valid filename part.

    Values for a fixable can be specified using a string expression of the following
    format ``start:stop[:step]``. This will generate values between 'start' and 'stop'
    spaced by 'step'. The 'stop' value will be included (``values <= stop``). The step
    is optional and will by default be one. It also does not need to be signed, only its
    absolute value will be used.

        "2000:2005": [2000, 2001, 2002, 2003, 2004, 2005]
        "2000:2005:2": [2000, 2002, 2004]
        "2005:2000:2": [2005, 2003, 2001]
        "0.:2.:0.5": [0.0, 0.5, 1.0, 1.5, 2.0]

    Parameters
    ----------
    trait
        Trait instance.
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
        if unicode:
            traits.append(Unicode())
        if range and isinstance(trait, tuple(RangeTrait.allowed_traits)):
            traits.append(RangeTrait(trait))
        else:
            traits.append(List(trait))

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
            fullname = f"{obj.__module__}.{obj.__name__}"
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

    def serialize(obj: t.Any) -> str:
        """Return the full import name of any object or type."""
        if isinstance(obj, type):
            cls = obj
        else:
            cls = obj.__class__
        name = cls.__name__
        module = cls.__module__

        # fullname (default)
        out = f"{module}.{name}"
        # if short we add tilde
        if mode == "short":
            out = f"~{out}"
        # if minimal only keep the name
        elif mode == "minimal":
            out = name

        return out

    def recurse(obj):
        """Recurse this function, keeping optional arguments."""
        return get_trait_typehint(obj, mode, aliases)

    def output(typehint):
        """Hook before returning the typehint."""  # noqa: D401
        if (alias := aliases.get(typehint.lstrip("~"), None)) is not None:
            typehint = alias
        if trait.allow_none:
            typehint += " | None"
        return typehint

    # Get the typehint of the trait itself
    typehint = serialize(trait)

    # If simply an object, nothing specific to do:
    if not isinstance(trait, TraitType):
        return typehint

    if isinstance(trait, Union):
        interior = " | ".join(recurse(subtrait) for subtrait in trait.trait_types)
        return output(interior)

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
                key_val[0] = "~typing.Any"

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
        interior = recurse(trait._trait)
        return output(f"{typehint}[{interior}]")

    if isinstance(trait, Type | Instance):
        if isinstance(trait.klass, str):
            interior = trait.klass
        else:
            interior = recurse(trait.klass)
        return output(f"{typehint}[{interior}]")

    return output(typehint)
