from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .dataset import DatasetAbstract


log = logging.getLogger(__name__)


class Assistant:
    METHODS_TO_DEFINE: Sequence[str] = []

    def __init__(self, dataset: DatasetAbstract):
        self.dataset = dataset
        self.cache: dict[str, Any] = {}
        self.auto_cache: dict[str, tuple[Callable, list, dict]] = {}

    def run_on_dataset(self, method: str, *args, **kwargs):
        if hasattr(self.dataset, method) and callable(getattr(self.dataset, method)):
            func = getattr(self.dataset, method)

            # We use PARAMS_NAMES instead of allowed_params which contains
            # fixables, which can be missing in some operations
            missing = [p for p in self.dataset.PARAMS_NAMES
                       if p not in self.dataset.params]
            if missing:
                log.warning('Possibly missing parameters %s', str(missing))

            return func(*args, **kwargs)
        else:
            classname = self.dataset.__class__.__name__
            msg = f"{classname} has no callable method '{method}'."
            if method in self.METHODS_TO_DEFINE:
                msg += f" You must subclass {classname} and define '{method}'."
            raise AttributeError(msg)

    def _reset_cached_properties(self) -> None:
        self.cache = {}

    def get_cached(self, key: str) -> Any:
        if key in self.cache:
            return self.cache[key]
        if key in self.auto_cache:
            func, args, kwargs = self.auto_cache[key]
            value = func(*args, **kwargs)
            self.cache[key] = value
            return value
        raise KeyError(f"Key '{key}' not found in cache or auto_cache")

    def define_auto_cache(self, key, method, *args, **kwargs):
        self.auto_cache[key] = (method, args, kwargs)
