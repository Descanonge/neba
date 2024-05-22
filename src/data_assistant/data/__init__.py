"""Define easily classes to deal with your many datasets."""

from .data_manager import DataManagerBase
from .loader import LoaderPluginAbstract
from .plugin import CachePlugin, Plugin, autocached
from .register import DatasetStore
from .source import FileFinderPlugin, GlobPlugin, MultiFilePluginAbstract
from .writer import WriterMultiFilePluginAbstract, WriterPluginAbstract

__all__ = [
    "CachePlugin",
    "DataManagerBase",
    "DatasetStore",
    "GlobPlugin",
    "FileFinderPlugin",
    "LoaderPluginAbstract",
    "MultiFilePluginAbstract",
    "Plugin",
    "WriterMultiFilePluginAbstract",
    "WriterPluginAbstract",
    "autocached",
]
