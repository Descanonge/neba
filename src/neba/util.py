"""Various utilities."""

import importlib
import typing as t


def import_item(name: str) -> t.Any:
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


def get_classname(cls: t.Any, module: bool = True) -> str:
    """Return fullname of a class."""
    if not isinstance(cls, type):
        cls = type(cls)

    elements = []
    if module:
        elements.append(cls.__module__)

    elements.append(getattr(cls, "__qualname__", cls.__name__))

    return ".".join(elements)
