from data_assistant.dataset import DataManagerBase
from data_assistant.dataset.xarray import (
    XarrayMultiFileLoaderPlugin,
    XarraySplitWriterPlugin,
)


class DMSST(XarrayMultiFileLoaderPlugin, XarraySplitWriterPlugin, DataManagerBase):
    PARAMS_NAMES = ["days", "region"]

    PARAMS_DEFAULTS = dict(days=5)

    def get_root_directory(self):
        return [str(self.params["days"]), "SST"]

    def get_filename_pattern(self):
        return "%(Y)/SST_%(Y)%(m)%(d).nc"


if __name__ == "__main__":
    dm = DMSST()
