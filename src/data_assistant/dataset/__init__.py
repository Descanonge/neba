from .dataset import DatasetBase
from .register import DatasetStore

from .file_manager import FileFinderModule, climato
from .loader import XarrayMultiFileLoaderModule
from .writer import XarraySplitWriterModule


__all__ = ["DatasetBase", "DatasetDefault", "DatasetStore", "climato"]


class DatasetDefault(
    XarrayMultiFileLoaderModule, XarraySplitWriterModule, FileFinderModule, DatasetBase
):
    pass
