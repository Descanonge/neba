from __future__ import annotations

from collections.abc import Mapping

from typing import Any, TYPE_CHECKING

import xarray as xr

from .util import Module
from .file_manager import FileFinderManager

if TYPE_CHECKING:
    import xarray as xr



class WriterAbstract(Module):
    pass
