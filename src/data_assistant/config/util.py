from collections.abc import Callable
from typing import Any

from traitlets.config import Configurable
from traitlets.traitlets import Container, Dict, Instance, TraitType, Tuple, Type, Union


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


def indent(lines: list[str], num: int = 4) -> list[str]:
    for i, line in enumerate(lines):
        lines[i] = " " * num + line
    return lines


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
