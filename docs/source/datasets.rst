
.. currentmodule:: data_assistant.data

******************
Dataset management
******************

This package has a submodule :mod:`~data_assistant.data` to ease the creation
and management of multiple dataset with different file format, structure, etc.
that can all depend on various parameters.

Each new dataset is specified by creating a new subclass of
:class:`~.DataManagerBase`. Relevant attributes or methods are overridden to
provide information on this dataset. For example a method that return the data
files can be overwritten by the user to cater to *this dataset*. Each instance
of this new subclass corresponds to a set of parameters that can be used to
change aspects of the dataset on the fly: choose only files for a specific year,
change the method to open data, etc.

.. _plugin-system:

Plugin system
=============

This framework tries to make those data managers objects as universal as
reasonably possible. The base class do not specify a data source (it could be
one file, multiple files, network datastore, ...) or a data type. The management
of parameters is also not implemented. Features can be added to the data manager
class as needed via a system of independent plugins.

.. note::

   Each plugin is a mixin: a class that is not intended to work on its own, but
   as a additional parent of the user data manager class.

   Plugins are subclasses of :class:`.Plugin`. On instanciation, the
   data manager detects them and call :meth:`.Plugin._init_plugin` on
   every plugin that is a direct parent of the manager class. This allows to
   initialize every plugin.

For example, we can make a straightforward dataset class by having the plugins
:class:`params.ParamsMappingPlugin` to store parameters in a dictionary,
:class:`xarray.XarrayFileLoaderPlugin` and :class:`xarray.XarrayWriterPlugin` to
load and write data using :mod:`xarray`. For finding our data file, we will
directly overwrite :meth:`.DataManagerBase.get_source`, which will be used by
:meth:`.LoaderPluginAbstract.get_data` (and from which other loaders are
derived)::

    class DatasetSimple(
        XarrayFileLoaderPlugin,
        XarrayWriterPlugin,
        ParamsMappingPlugin,
        DataManagerBase
    ):

        def get_source(self):
            """Should return a file for XarrayFileLoaderPlugin."""
            # we can use the parameters stored DataManagerBase
            if self.params["method"] == 1:
                return "file_1"
            else:
                return "file_2"

.. note::

   Remember that for multiple inheritance, parent classes on the left have
   higher priority. The DataManagerBase thus should be the last base class.
   See :external+python:ref:`tut-inheritance`.

Let's switch to datasets that comprise of multiple files, we can use either
:class:`source.GlobPlugin`, or :class:`source.FileFinderPlugin` to find and
manage datafiles using the simple syntax of :mod:`filefinder`. We appropriately
switch to :class:`xarray.XarrayMultiFileLoaderPlugin` to deal with multi-file
inputs::

    class DatasetMultifile(
        XarrayMultiFileLoaderPlugin,
        XarrayWriterPlugin,
        FileFinderPlugin,
        ParamsMappingPlugin,
        DatasetBase,
    ):
        OPEN_MFDATASET_KWARGS = dict(parallel=True)

        def get_root_directory(self):
            return "/data/SST"

        def get_filename_pattern(self):
            return "%(Y)/SST_%(Y)%(m)%(d).nc"


.. note::

   Non-essential dependencies are loaded lazily as much as possible. This is
   why all xarray related plugins are put in their own submodule
   :mod:`.data.xarray` (that is not imported in the top-level `__init__`).

Plugin interplay
================

For the most part, plugins are made to be independent of each others, but it can
be useful to have interplay. We have already seen some communications between
plugins via abstract methods of the data manager like
:meth:`.DataManagerBase.get_source` or
:meth:`.DataManagerBase.get_data`.
The same goes for parameters management: abstract methods are defined directly
in the DataManagerBase, since they are necessary.

We also have seen that plugins can inherit from abstract classes, such that
it can be expected that they implement some specific methods: see
:class:`loader.LoaderPluginAbstract`, :class:`writer.WriterPluginAbstract`,
:class:`writer.WriterMultiFilePluginAbstract`, or
:class:`source.MultiFilePluginAbstract`.

If two specific plugins must directly interact, we can check the presence of a
specific plugin via ``isinstance(self, SpecificPlugin)``. We can also simply
create a "merger" plugin that inherits from the two plugins that need to
interact. For instance we combine the writing plugin with the filefinder one,
giving :class:`xarray.XarraySplitWriterPlugin`, so that we can automatically
split data to different files when writing to disk using the specified filename
pattern::

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


Dataset parameters
==================

A dataset instance is supposed to represent a specific set of parameters.
Changing parameters might affect plugins, and thus it is recommended to change
parameters using :class:`.DataManagerBase.set_params`.
After the parameters have been modified, this function will launch all callbacks
that have been registered by plugins. For instance, some plugins may use a cache
and need to void it after a parameters change.

It might be useful to quickly change parameters, eventually multiple times,
before returning to the initial set of parameters. To this end, the method
:meth:`.DataManagerBase.save_excursion` will return a context manager that will
save the initial parameters and restore them when exiting::

    # we have some parameters, self.params["p"] = 0

    with self.save_excursion():
        # we change them
        self.set_params(p=2)
        self.get_data()

    # we are back to self.params["p"] = 0

.. note::

    If there are caches, their contents will not be saved by default. This can
    be activated with ``save_cache=True``. However, the logic behind the context
    manager is pretty simple and restoring caches might lead to unforeseen
    consequences.

As noted above, how parameters are stored and managed is to be specified by
choosing a plugin. The simplest is :class:`.ParamsMappingPlugin` that
stores parameters in a dictionary attribute ``params``.

The package also provides :class:`.ParamsSchemePlugin` where parameters are
stored in a :class:`data_assistant.config.scheme.Scheme` object. By specifying
the exact expected type of the parameters, this can ensure the existence of
parameters::

    class MyParameters(Scheme):
        threshold = Float(0.5)

    class Dataset(ParamsSchemePlugin, DataManagerBase):

        params: MyParameters

Now we are sure that ``Dataset().params`` will contain a ``threshold``
attribute. This comes at the cost of flexibility since schemes are not as
malleable as other mapping types as it only implements :meth:`~.Scheme.update`
(see :ref:`mapping-interface`).

The parameters plugins should implement :meth:`~.DataManagerBase.params_as_dict`
to return the parameters as a dictionary, and others plugins are encouraged to
use it to facilitate interface.

.. _cache-plugin:

Cache plugin
============

.. note::

   This section is aimed at plugin writers. Users can safely ignore it.

It might help for some plugins to have a cache to write information into. For
instance plugins managing source consisting of multiple files leverage this. The
caches of different plugins need to be separated to avoid name clashes and other
potential problems. However this pretty much requires to hardcode the cache
location.

To integrate a new cache into the rest of a DataManager compound, it is
advised (but technically not required) to do the following when creating
a :class:`.CachePlugin` subclass:

* In ``_init_plugin``:

  * create a cache attribute. A simple :class:`dict` suffices. Its name should
    not clash with existing attributes.
  * append this attribute name to :attr:`.CachePlugin._CACHE_LOCATION`, this
    let know other plugins where are the different caches. Notably,
    :class:`.CachePlugin` will automatically register a callback to clear the
    caches after a parameters change.
  * do not forget to call ``super().__init___`` to do this registration,
    **after _CACHE_LOCATION has been updated**.

* You can eventually create an *autocached* decorator using
  :func:`.plugin.get_autocached`. It will make any property automatically
  cached: if a value exists in the cache it is returned immediately, otherwise
  the code defined in the property is run and the result is cached for later.

Let's take all this into a simple example::

    class MultifilePlugin(CachePlugin):

        # create a decorator, scope is the class
        _autocached = get_autocached("_mulfifile_cache")

        def _init_plugin(self) -> None:
            self._multifile_cache = {}
            self._CACHE_LOCATIONS.add("_multifile_cache")
            super().__init__()

        @property
        @_autocached
        def datafiles(self) -> list[str]:
            ...
            # some long and complicated code to obtain our files
            ....
            return filelist


We run here into a inherent problem of the plugin/mixin system. Attributes
defined in subclasses of plugins can be somewhat complex because there is
no easy way to know at runtime to which plugin an attribute is associated to.
At runtime, everything is bound to the same object: a class with a
DataManagerBase and multiple plugins as parents.

For the cache this translates into a difficulty to separate different caches
from different plugins.

.. note::

   It is technically possible to do this programmatically using the
   :mod:`inspect` module. But this is not trivial: we need to find the right
   frame to find the information we need. Go back to
   ``DataManagerBase.__init___`` to get the *cls* variable for instance. The
   pitfalls far outweigh the benefit of having a little less to write.
