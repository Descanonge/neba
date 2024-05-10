"""Define easily classes to deal with your many datasets."""

from .data_manager import DataManagerBase
from .loader import LoaderPluginAbstract
from .plugin import CachePlugin, Plugin, autocached
from .register import DatasetStore
from .source import GlobPlugin, MultiFilePluginAbstract
from .writer import WriterMultiFilePluginAbstract, WriterPluginAbstract

__all__ = [
    "CachePlugin",
    "DataManagerBase",
    "DatasetStore",
    "GlobPlugin",
    "LoaderPluginAbstract",
    "MultiFilePluginAbstract",
    "Plugin",
    "WriterMultiFilePluginAbstract",
    "WriterPluginAbstract",
    "autocached",
]
