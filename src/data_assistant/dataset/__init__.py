"""Define easily classes to deal with your many datasets."""

from .dataset import DataManagerBase
from .register import DatasetStore

__all__ = ["DataManagerBase", "DatasetStore"]
