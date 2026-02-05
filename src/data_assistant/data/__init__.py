"""Define easily classes to deal with your many datasets."""

from .dataset import Dataset
from .loader import LoaderAbstract
from .module import CachedModule, Module, autocached
from .params import (
    ParamsManagerAbstract,
    ParamsManagerApp,
    ParamsManagerDict,
    ParamsManagerSection,
)
from .source import (
    FileFinderSource,
    GlobSource,
    MultiFileSource,
    SimpleSource,
    SourceAbstract,
    SourceIntersection,
    SourceUnion,
)
from .store import DatasetStore
from .util import import_all
from .writer import Splitable, SplitWriterMixin, WriterAbstract

__all__ = [
    "CachedModule",
    "Dataset",
    "DatasetStore",
    "FileFinderSource",
    "GlobSource",
    "LoaderAbstract",
    "Module",
    "MultiFileSource",
    "ParamsManagerDict",
    "ParamsManagerAbstract",
    "ParamsManagerApp",
    "ParamsManagerSection",
    "ParamsMap",
    "SimpleSource",
    "SourceAbstract",
    "SourceIntersection",
    "SourceUnion",
    "SplitWriterMixin",
    "Splitable",
    "WriterAbstract",
    "autocached",
    "import_all",
]
