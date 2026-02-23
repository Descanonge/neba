"""Define easily classes to deal with your many datasets."""

from .interface import DataInterface, DataInterfaceSection
from .loader import LoaderAbstract
from .module import CachedModule, Module, autocached
from .params import (
    ParametersAbstract,
    ParametersApp,
    ParametersDict,
    ParametersSection,
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
from .store import DataInterfaceStore
from .writer import (
    MetadataGenerator,
    Splitable,
    SplitWriterMixin,
    WriterAbstract,
    element,
)

__all__ = [
    "CachedModule",
    "DataInterface",
    "DataInterfaceSection",
    "DataInterfaceStore",
    "FileFinderSource",
    "GlobSource",
    "LoaderAbstract",
    "MetadataGenerator",
    "Module",
    "MultiFileSource",
    "ParametersAbstract",
    "ParametersApp",
    "ParametersDict",
    "ParametersSection",
    "SimpleSource",
    "SourceAbstract",
    "SourceIntersection",
    "SourceUnion",
    "SplitWriterMixin",
    "Splitable",
    "WriterAbstract",
    "autocached",
    "element",
]
