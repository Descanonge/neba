
.. currentmodule:: neba.data

******************
Dataset management
******************

Neba tries to ease the creation and management of multiple datasets with
different file format, structure. Each new dataset is specified by creating a
subclass of :class:`~.Dataset`. It contains interchangeable *modules* that each
cover some functionalities. One dataset can deal with multiple source files
selected via glob patterns, loaded into pandas, while another could have a
remote data-store as input loaded into xarray.


Here is a example::


   from neba.data import Dataset, ParamsManagerDict, GlobSource
   from neba.data.xarray import XarrayLoader

   class SST(Dataset):

      ParamsManager = ParamsManagerDict
      Loader = XarrayLoader
      Loader.OPEN_MFDATASET_KWARGS = dict(parallel=True)

      class Source(GlobSource):
         def get_root_directory(self):
            return "/data"

         def get_glob_pattern(self):
            return f"{self.params['year']}/SST_*.nc"

    dm = SST()
    sst = dm.get_data()

.. toctree::
   :hidden:

   usage

   existing_modules
