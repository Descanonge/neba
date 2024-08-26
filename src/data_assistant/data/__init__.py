"""Define easily classes to deal with your many datasets."""

from .data_manager import DataManagerBase
from .loader import LoaderAbstract
from .module import CachedModule, Module, autocached
from .params import ParamsManager, ParamsManagerAbstract, ParamsManagerScheme
from .register import DatasetStore
from .source import FileFinderSource, GlobSource, MultiFileSource, SimpleSource
from .writer import CachedWriter, WriterAbstract

__all__ = [
    "CachedModule",
    "CachedWriter",
    "DataManagerBase",
    "DatasetStore",
    "FileFinderSource",
    "GlobSource",
    "LoaderAbstract",
    "Module",
    "MultiFileSource",
    "ParamsManager",
    "ParamsManagerAbstract",
    "ParamsManagerScheme",
    "ParamsMap",
    "SimpleSource",
    "WriterAbstract",
    "autocached",
]
