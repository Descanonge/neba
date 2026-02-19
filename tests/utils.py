"""Utilities for tests."""

import keyword
from typing import Protocol, TypeVar

from hypothesis import strategies as st
from traitlets import TraitType

P = TypeVar("P")
T_Trait = TypeVar("T_Trait", bound=TraitType)


class Drawer(Protocol):
    """Drawing function."""

    def __call__(self, __strat: st.SearchStrategy[P]) -> P: ...


valid = "".join(chr(i) for i in range(97, 123))
valid += valid.upper()
valid += "".join(str(i) for i in range(10))
valid += "_"
st_varname = (
    st.text(alphabet=valid, min_size=1, max_size=16)
    .filter(lambda s: not s.startswith("_"))
    .filter(lambda s: s.isidentifier())
    .filter(lambda s: not keyword.iskeyword(s))
)
