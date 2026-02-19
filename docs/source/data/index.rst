
.. currentmodule:: neba.data

***************
Data management
***************

Neba tries to ease the creation and management of multiple datasets with
different file formats, structures, etc. One dataset can have with multiple
source files selected via glob patterns, loaded into pandas, while another could
have xarray load a remote data-store.

Each new dataset is specified by creating a subclass of
:class:`~.DataInterface`. It can then be re-used in various scripts to read or
write data easily. The interface contains interchangeable *modules* that are
tasked with managing parameters, retrieving data locations, loading and writing
data. Their behavior can depend on parameters held by the interface.

Here is a example::

   from neba.data import DataInterface, ParametersDict, GlobSource
   from neba.data.xarray import XarrayLoader

   class SST(DataInterface):

      # store parameters in a simple dict
      Parameters = ParametersDict

      # load data using xarray
      Loader = XarrayLoader
      Loader.open_mfdataset_kwargs = dict(parallel=True)

      # find files on disk using glob
      class Source(GlobSource):
         def get_root_directory(self):
            return "/data"

         def get_glob_pattern(self):
            return f"{self.parameters['year']}/SST_*.nc"

    di = SST(year=2000)
    sst = di.get_data()

.. toctree::
   :hidden:

   usage

   existing_modules
