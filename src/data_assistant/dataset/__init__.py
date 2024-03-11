"""Define easily classes to deal with your many datasets."""

from .dataset import DataManagerBase
from .file_manager import FileFinderModule, climato
from .loader import XarrayMultiFileLoaderModule
from .register import DatasetStore
from .writer import XarraySplitWriterModule

__all__ = ["DataManagerBase", "DatasetDefault", "DatasetStore", "climato"]


class DatasetDefault(
    XarrayMultiFileLoaderModule,
    XarraySplitWriterModule,
    FileFinderModule,
    DataManagerBase,
):
    pass
