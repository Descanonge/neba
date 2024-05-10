
.. currentmodule:: data_assistant.data

Dataset management
==================

This package has a submodule :mod:`~data_assistant.data` to ease the creation
and management of multiple dataset with different file format, structure, etc.
that can all depend on various parameters.

Each new dataset is specified by creating a new subclass of
:class:`~data_manager.DataManagerBase`.
Relevant attributes or methods are overridden to provide information on this
dataset. For example a method that return the data files can be overwritten by
the user to cater to *this dataset*.
Each instance of this new subclass corresponds to a set of parameters that can
be used to change aspects of the dataset on the fly: choose only files for a
specific year, change the method to open data, etc.

Plugin system
-------------

This framework tries to make those data managers objects as universal as
reasonably possible.
The base classes do not have a data source (it could be one file, multiple
files, network datastore, ...) or a data type specified.
Features can be added to the data manager class as needed via a system of
independent plugins.

.. note::

   Each plugin is a mixin: a class that is not intended to work on its own, but
   as a additional parent of the user data manager class.

   Plugins are subclasses of :class:`~plugin.Plugin`. On instanciation, the
   data manager detects them and call :meth:`plugin.Plugin._init_plugin` on
   every plugin that is a direct parent of the manager class. This allows to
   initialize every plugin.

For example, we can make a straightforward dataset class by having the plugins
:class:`xarray.XarrayFileLoaderPlugin` and :class:`xarray.XarrayWriterPlugin` to
load and write data using :mod:`xarray`.
For finding our data file, we will directly overwrite
:meth:`DataManagerBase.get_source<data_manager.DataManagerBase.get_source>`,
which will be used by
:meth:`LoaderPluginAbstract.get_data<loader.LoaderPluginAbstract.get_data>` (and
from which other loaders are derived)::

    class DatasetSimple(
        XarrayFileLoaderPlugin, XarrayWriterPlugin, DataManagerBase
    ):

        def get_source(self):
            """Should return a file for XarrayFileLoaderPlugin."""
            # we can use the parameters stored by DataManagerBase
            if self.params["method"] == 1:
                return "file_1"
            else:
                return "file_2"
      
Let's switch to datasets that comprise of multiple files, we can use either
:class:`source.GlobPlugin` or :class:`filefinder.FileFinderPlugin` to find and
manage datafiles using the simple syntax of :mod:`filefinder`. We appropriately
switch to :class:`xarray.XarrayMultiFileLoaderPlugin` to deal with multi-file
inputs::

    class DatasetMultifile(
        XarrayMultiFileLoaderPlugin,
        XarrayWriterPlugin,
        FileFinderPlugin,
        DatasetBase,
    ):
        OPEN_MFDATASET_KWARGS = dict(parallel=True)

        def get_root_directory(self):
            return "/data/SST"

        def get_filename_pattern(self):
            return "%(Y)/SST_%(Y)%(m)%(d).nc"


.. note::

   You may have noticed that plugins that depend on a optional packages are
   put in separate submodules. This helps with loading only the necessary
   modules in a simple manner.

Plugin interplay
----------------

For the most part, plugins are made to be independent of each others, but it can
be useful to have interplay. We have already seen some communications between
plugins via abstract methods of the data managers like
:meth:`~data_manager.DataManagerBase.get_source` or
:meth:`~data_manager.DataManagerBase.get_data`.
We also have seen that plugins can inherit from abstract classes, such that
it can be expected that they implement some specific methods: see
:class:`loader.LoaderPluginAbstract`, :class:`writer.WriterPluginAbstract`,
:class:`writer.WriterMultiFilePluginAbstract`, or
:class:`source.MultiFilePluginAbstract`.

If two specific plugins must directly interact, we can check the presence of a
specific plugin via ``isinstance(self, SpecificPlugin)``. To avoid that, we can
also simply create a "merger" plugin that inherits from the two plugins that
need to interact.
For instance we combine the writing plugin with the filefinder one, giving
:class:`xarray.XarraySplitWriterPlugin`, so that we can automatically split data
to different files when writing to disk using the specified filename pattern::

    class DatasetMultifile(
        XarrayMultiFileLoaderPlugin, XarraySplitWriterPlugin, DatasetBase
    ):
        ...

Say we obtain our SST dataset as a :class:`xarray.Dataset`, we can write our
daily data to disk in monthly files. It would also distribute among any other
parameters present in the filename pattern. And by supplying a Dask client, this
is going to be done in parallel::

    SST(**maybe_our_parameters).write(
        sst,
        time_freq="M",
        client=client
    )

Cache plugin
------------

Plugins can inherit from :class:`plugin.CachePlugin`, giving them access to
a cache to store information (and hopefully speed things a bit).
However, we must not forget that plugins are mixins to the data manager claas.
This means the cache is a simple dictionary attribute **that is shared by all
plugins**.

.. note::

    A plugin could thus erase or replace keys from another plugin. Automatically
    separating caches from different plugins is difficult, even with
    introspection (at runtime, all methods are bound to the same data manager
    object).

    There is currently no proposed solution other than hard-coded keys so that
    they are attached to their plugin, using the plugin class name for instance.
    This is done automatically when using the :func:`~.plugin.autocached`
    decorator on properties. This automatically use the key
    ``{plugin_class_name}::{property_name}``.

Dataset parameters
------------------

.. currentmodule:: data_assistant.data.data_manager

A dataset instance is supposed to represent a specific set of parameters.
Changing parameters might affect plugins, and thus it is recommended to change
parameters using
:class:`DataManagerBase.set_params`.
This will ensure that all callbacks registered by plugins are called. Most
pro-eminently, **changing parameters will void the cache** (if there is a
cache plugin).

It might be useful to quickly change parameters, eventually multiple times,
before returning to the initial set of parameters. To this end, the method
:meth:`DataManagerBase.save_excursion` will return a context manager that will
save the initial parameters and restore them when exiting::

    # we have some parameters, self.params["p"] = 0

    with self.save_excursion():
        # we change them
        self.set_params(p=2)
        self.get_data()

    # we are back to self.params["p"] = 0

.. note::

    If there is a cache, its contents will not be saved by default. This can be
    activated with ``save_cache=True``. However, the logic behind the context
    manager is pretty simple and restoring the cache might lead to unforeseen
    consequences.
