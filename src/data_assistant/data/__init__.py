"""Define easily classes to deal with your many datasets."""

from .dataset import Dataset
from .loader import LoaderAbstract
from .module import CachedModule, Module, autocached
from .params import (
    ParamsManager,
    ParamsManagerAbstract,
    ParamsManagerApp,
    ParamsManagerSection,
)
from .register import DatasetStore
from .source import (
    FileFinderSource,
    GlobSource,
    MultiFileSource,
    SimpleSource,
    SourceIntersection,
    SourceUnion,
)
from .util import import_all
from .writer import CachedWriter, Splitable, SplitWriterMixin, WriterAbstract

__all__ = [
    "CachedModule",
    "CachedWriter",
    "Dataset",
    "DatasetStore",
    "FileFinderSource",
    "GlobSource",
    "LoaderAbstract",
    "Module",
    "MultiFileSource",
    "ParamsManager",
    "ParamsManagerAbstract",
    "ParamsManagerApp",
    "ParamsManagerSection",
    "ParamsMap",
    "SimpleSource",
    "SourceIntersection",
    "SourceUnion",
    "SplitWriterMixin",
    "Splitable",
    "WriterAbstract",
    "autocached",
    "import_all",
]
