from .dataset import DatasetBase, climato
from .register import DatasetStore

from .file_manager import FileFinderMixin
from .loader import XarrayMultiFileMixin
from .writer import XarraySplitWriter


__all__ = ["DatasetBase", "DatasetDefault", "DatasetStore", "climato"]


class DatasetDefault(
    XarrayMultiFileMixin, XarraySplitWriter, FileFinderMixin, DatasetBase
):
    pass
