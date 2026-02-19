"""Various utilities."""

import importlib
import itertools
from collections.abc import Iterable
from typing import Any

import Levenshtein


def import_item(name: str) -> Any:
    """Import item. Expected to import an item inside a module."""
    parts = name.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError("Can only import objects inside module")
    module_name, obj_name = parts
    module = importlib.import_module(module_name)
    try:
        obj = getattr(module, obj_name)
    except AttributeError as e:
        raise ImportError(f"No object named {obj_name} in module {module_name}") from e
    return obj


def get_classname(cls: Any, module: bool = True) -> str:
    """Return fullname of a class."""
    if not isinstance(cls, type):
        cls = type(cls)

    elements = []
    if module:
        elements.append(cls.__module__)

    elements.append(getattr(cls, "__qualname__", cls.__name__))

    return ".".join(elements)


def cut_in_slices(total_size: int, slice_size: int) -> list[slice]:
    """Return list of slices of size at most ``slice_size``."""
    slices = itertools.starmap(
        slice,
        itertools.pairwise(itertools.chain(range(0, total_size, slice_size), [None])),
    )
    return list(slices)


def did_you_mean(suggestions: Iterable[str], wrong_key: str) -> str | None:
    """Return element of `suggestions` closest to `wrong_key`."""
    min_distance = 9999
    closest_key = None
    for suggestion in suggestions:
        distance = Levenshtein.distance(suggestion, wrong_key)
        if distance < min_distance:
            min_distance = distance
            closest_key = suggestion

    return closest_key
