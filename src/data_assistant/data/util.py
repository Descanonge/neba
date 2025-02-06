import typing as t
from collections import abc

T_Data = t.TypeVar("T_Data")
"""Type of data (numpy, pandas, xarray, etc.)."""
T_Source = t.TypeVar("T_Source")
"""Type of the data source (filename, URL, object, etc.)."""
T_Params = t.TypeVar("T_Params")
"""Type of the parameters storage."""


def import_all(file, /) -> None:
    """Import everything in the directory of a given file.

    Can be used to quickly import all datasets and make them available as configurable
    sections.

    Can be passed ``__file__`` for instance. Private modules (starting with _) are not
    imported.
    """
    import importlib
    import os
    from glob import glob
    from os import path

    file = path.relpath(file, os.getcwd())
    directory = path.dirname(file)

    files = glob(path.join(directory, "*.py"))
    files = [
        path.splitext(f)[0].replace(os.sep, ".")
        for f in files
        if path.isfile(f) and f != file and not path.basename(f).startswith("_")
    ]

    for f in files:
        importlib.import_module(f)
