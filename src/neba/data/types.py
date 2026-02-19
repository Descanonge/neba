"""Various itilities."""

from typing import TypeVar

T_Data = TypeVar("T_Data")
"""Type of data (numpy, pandas, xarray, etc.)."""
T_Source = TypeVar("T_Source")
"""Type of the data source (filename, URL, object, etc.)."""
T_Params = TypeVar("T_Params")
"""Type of the parameters storage."""

T_Source_co = TypeVar("T_Source_co", covariant=True)
"""For Source (the source is an output)."""
T_Source_contra = TypeVar("T_Source_contra", contravariant=True)
"""For Loader and Writer (the source an input)."""
