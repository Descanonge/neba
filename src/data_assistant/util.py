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
