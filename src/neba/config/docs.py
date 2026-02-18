"""Documentation related utilities."""

import typing as t
from collections import abc

from traitlets.traitlets import Container, Dict, Instance, TraitType, Tuple, Type, Union
from traitlets.utils.text import wrap_paragraphs

from neba.utils import get_classname


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


def stringify(obj: t.Any, rst: bool = True) -> str:
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

    def recurse(obj: t.Any) -> str:
        """Recurse this function, keeping optional arguments."""
        return get_trait_typehint(obj, mode, aliases)

    def output(typehint: str, add_none: bool = False) -> str:
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
