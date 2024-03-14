"""Define easily classes to deal with your many datasets."""

from .data_manager import DataManagerBase
from .register import DatasetStore

__all__ = ["DataManagerBase", "DatasetStore"]
