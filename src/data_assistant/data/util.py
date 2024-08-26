import typing as t
from collections import abc

from ..config import Scheme

T_Data = t.TypeVar("T_Data")
"""Type of data (numpy, pandas, xarray, etc.)."""
T_Source = t.TypeVar("T_Source")
"""Type of the data source (filename, URL, object, etc.)."""
T_Params = t.TypeVar("T_Params")
"""Type of the parameters storage."""
