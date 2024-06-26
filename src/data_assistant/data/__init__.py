"""Define easily classes to deal with your many datasets."""

from .data_manager import DataManagerBase
from .loader import LoaderPluginAbstract
from .params import ParamsMappingPlugin, ParamsSchemePlugin
from .plugin import CachePlugin, Plugin, get_autocached
from .register import DatasetStore
from .source import FileFinderPlugin, GlobPlugin, MultiFilePluginAbstract
from .writer import WriterPluginAbstract

__all__ = [
    "CachePlugin",
    "DataManagerBase",
    "DatasetStore",
    "GlobPlugin",
    "FileFinderPlugin",
    "LoaderPluginAbstract",
    "MultiFilePluginAbstract",
    "ParamsMap",
    "ParamsMappingPlugin",
    "ParamsSchemePlugin",
    "Plugin",
    "WriterPluginAbstract",
    "get_autocached",
]
