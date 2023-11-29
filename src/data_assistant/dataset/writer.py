from __future__ import annotations

from collections.abc import Mapping

from typing import Any, TYPE_CHECKING

import xarray as xr

from .file_manager import FileFinderManager
from .module import Module

if TYPE_CHECKING:
    import xarray as xr



class WriterAbstract(Module):
    pass
