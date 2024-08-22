"""Define easily classes to deal with your many datasets."""

from .data_manager import DataManagerBase
from .loader import LoaderModule
from .module import CachedModule, Module, autocached
from .params import ParamsManager, ParamsManagerModule, ParamsManagerScheme
from .register import DatasetStore
from .source import FileFinderSource, GlobSource, MultiFileSource, SimpleSource
from .writer import CachedWriter, WriterModule

__all__ = [
    "CachedModule",
    "CachedWriter",
    "DataManagerBase",
    "DatasetStore",
    "FileFinderSource",
    "GlobSource",
    "LoaderModule",
    "Module",
    "MultiFileSource",
    "ParamsManager",
    "ParamsManagerModule",
    "ParamsManagerScheme",
    "ParamsMap",
    "SimpleSource",
    "WriterModule",
    "autocached",
]
