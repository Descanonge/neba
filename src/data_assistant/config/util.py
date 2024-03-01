import re
from collections.abc import Callable, Sequence
from typing import Any

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
    The trait type must be one of :attr:`range_trait` (by default float or int).
    Here are some examples:

        "2000:2005": [2000, 2001, 2002, 2003, 2004, 2005]
        "2000:2005:2": [2000, 2002, 2004]
        "2005:2000:2": [2005, 20003, 2001]
        "0.:2.:0.5": [0.0, 0.5, 1.0, 1.5, 2.0]

    Parameters
    ----------
    trait
        The trait corresponding to the fixable parameter format. Some of its properties
        are used: ``default_value``, ``allow_none``, ``help``. The metadata is not kept.
    kwargs
        Arguments passed to the Union trait created.
    """

    range_max_len: int = 500
    range_rgx = re.compile("(.+?):(.+?)(?::(.*?))?")
    range_trait: list[type[TraitType]] = [Float, Int]

    info_text = "a fixable"

    def __init__(self, trait: TraitType, default_value: Any = None, **kwargs) -> None:
        self.trait = trait
        traits = [trait, Unicode(), List(trait)]
        for arg in ["default_value", "help", "allow_none"]:
            value = getattr(trait, arg, None)
            if value is not None:
                kwargs.setdefault(arg, value)
        if default_value is not None:
            kwargs["default_value"] = default_value
        super().__init__(traits, **kwargs)

    def from_string(self, s: str) -> Any:
        """Get a value from a config string.

        Will test for a string specifying a range.
        """
        # TODO error management ? see traitlets.Union.from_string
        if isinstance(self.trait, tuple(self.range_trait)):
            m = self.range_rgx.fullmatch(s)
            if m is not None:
                try:
                    return self.from_string_range(m)
                except Exception as err:
                    raise ValueError(f"Failed to parse range string '{s}") from err
        return super().from_string(s)

    def from_string_range(self, m: re.Match) -> Sequence[Any]:
        """Get a list of value from a range specification.

        Parameters
        ----------
        m
            Match object resulting from the pattern :attr:`range_rgx`.
            Should contain groups matching start, stop, and step, in this order, step
            being optional.
        """
        import operator as op

        args_str = dict(zip(["start", "stop", "step"], m.groups(default="1")))
        args = []
        for var, arg_str in args_str.items():
            arg = self.trait.from_string(arg_str)
            if arg is None:
                trait_cls = self.trait.__class__.__name__
                raise ValueError(f"Could not parse {var}={arg_str} into {trait_cls}")
            args.append(arg)

        start, stop, step = args
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

        if len(values) == self.range_max_len:
            raise IndexError(
                f"Range length exceding maximum length ({self.range_max_len}). "
                "Possible misstake, else change FixableTrait.range_max_len"
            )

        return values


def tag_all_traits(**metadata) -> Callable:
    """Tag all class-own traits.

    Parameters
    ----------
    metadata:
        Are passed to ``trait.tag(**metadata)``.
    """

    def decorator(cls: type[Configurable]):
        for trait in cls.class_own_traits().values():
            trait.tag(**metadata)
        return cls

    return decorator


def add_spacer(lines: list[str]) -> list[str]:
    if not lines[-1].endswith("\n"):
        lines.append("\n")
    return lines


def underline(lines: list[str], char: str = "=") -> list[str]:
    lines.append(char * len(lines[-1]))
    return lines


def indent(lines: list[str], num: int = 4, initial_indent: bool = True) -> list[str]:
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


def get_trait_typehint(trait: Any, mode: str = "short") -> str:
    """Return the typehint corresponding to a trait object.

    Parameters
    ----------
    trait:
        Trait instance. Also accept any other type of object.
    mode:
        If "short", add a ~ in front of the full typehint to only print the type name
        but still have a link.
    """

    def serialize(obj: Any) -> str:
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
        return get_trait_typehint(obj, mode)

    def output(typehint):
        """Hook before returning the typehint."""
        if trait.allow_none:
            typehint += " | None"
        return typehint

    # If simply an object, nothing specific to do:
    if not isinstance(trait, TraitType):
        return serialize(trait)

    # Get the typehint of the trait itself
    typehint = serialize(trait)

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
