from .dataset import DatasetBase
from .file_manager import FileFinderModule, climato
from .loader import XarrayMultiFileLoaderModule
from .register import DatasetStore
from .writer import XarraySplitWriterModule

__all__ = ["DatasetBase", "DatasetDefault", "DatasetStore", "climato"]


class DatasetDefault(
    XarrayMultiFileLoaderModule, XarraySplitWriterModule, FileFinderModule, DatasetBase
):
    pass
