from typing import Any

from .util import Assistant


class LoaderAbstract(Assistant):
    OPEN_MFDATASET_KWARGS: dict[str, Any] = {}
    """Arguments passed to :func:`xarray.open_mfdataset`."""
