"""Various itilities."""

import typing as t

T_Data = t.TypeVar("T_Data")
"""Type of data (numpy, pandas, xarray, etc.)."""
T_Source = t.TypeVar("T_Source")
"""Type of the data source (filename, URL, object, etc.)."""
T_Params = t.TypeVar("T_Params")
"""Type of the parameters storage."""

T_Source_co = t.TypeVar("T_Source_co", covariant=True)
"""For Source (the source is an output)."""
T_Source_contra = t.TypeVar("T_Source_contra", contravariant=True)
"""For Loader and Writer (the source an input)."""
