
.. currentmodule:: data_assistant

****************
Existing plugins
****************

The *DataManager* class is expected to be extended by plugins (see
:ref:`plugin-system`). Here is a quick description of plugins that are bundled
with this package.

The features managed by the plugins presented underneath inherit from abstract
classes that define the API for that feature. Note that they are not defined
through the :external+python:mod:`abc` module, and thus will not raise if
instanciated. These classes are more guidelines than strict protocols.

.. note:: For developers

    Nevertheless it is advised to keep a common signature for plugin subclasses,
    relying on keyword arguments if necessary. This helps ensure
    inter-operability even for complex (diamond-shaped) ancestors tree.

Parameters
==========

The first and **mandatory** plugin manages the parameters of the ``DataManager``
instance. As it is considered mandatory there is no abstract class: the abstract
methods to implement are already defined in :class:`.DataManagerBase`:

* :meth:`~.DataManagerBase.set_params`
* :meth:`~.DataManagerBase.update_params`
* :meth:`~.DataManagerBase.save_excursion`
* :meth:`~.DataManagerBase.params_as_dict`
* :meth:`~.DataManagerBase._reset_params`

The most straightforward way to manager parameters is to store theme into a
dictionary, which is what :class:`.ParamsMappingPlugin` does.

A :class:`.Scheme` can be used to store parameters using
:class:`.ParamsSchemePlugin`. It allows to use the parameters retrieval from
the :doc:`configuration<configuration>`, and restrict parameters to those
statically defined. Parameters can be added to the scheme at runtime though at
the plugin relies on :meth:`.Scheme.update`. The scheme to use must be specified
as a class attribute::

    class Parameters(Scheme):
        ...

    class MyDataManager(ParamsSchemePlugin, DataManagerBase):
        SCHEME = Parameters

.. important::

   Using a scheme is not extensively tested.

.. note:: For developers

   Currently there is no API to retrieve parameters values. That leaves freedom
   to the type of :attr:`.DataManagerBase.params`. However to allow other plugin
   to retrieve parameters it is advised that ``params`` implements the interface
   of a mapping (at least ``__getitem__``), which should be universal enough.
   This may be formalized more cleanly in the future.


Source
======

The data is found from a source: one or more files on disk, or a remote
data-store for instance. For simpler cases, it may be enough to rewrite
:meth:`.DataManagerBase.get_source`, for instance::

    class MyDataManager(DataManagerBase):

        def get_source(self):
            return "path/to/datafile"

For more complex case, a plugin can help. For datasets consisting of multiple
files the package provide two plugins that follow
:class:`.MultiFilePluginAbstract`. For both of them the user should implement
:meth:`~.MultiFilePluginAbstract.get_root_directory` which returns the directory
containing the files (as a path, or a list of folders).

The plugin :class:`.GlobPlugin` can find files on disk that follow a given
pattern, defined by :meth:`~.GlobPlugin.get_glob_pattern`. Files on disk
matching the pattern are cached and available at :meth:`~.GlobPlugin.datafiles`.
For instance::

    class MyDataManager(GlobPlugin, ParamsMappingPlugin, DataManagerBase):

        def get_root_directory(self):
            return ["/data", self.params["user"], "subfolder"]

        def get_glob_pattern(self):
            return "SST_*.nc"

    files = MyDataManager().get_source()

For a similar scenario of a dataset across many files (for different dates,
variables or parameters values) an even more precise solution is provided with
:class:`.FileFinderPlugin`. This plugin relies on the `filefinder
<https://filefinder.readthedocs.io/en/latest/>`__ package to find files
according to a specific filename pattern. For instance::

    class MyDataManager(FileFinderPlugin, ParamsMappingPlugin, DataManagerBase):

        def get_root_directory(self):
            return ["/data", self.params["user"], "subfolder"]

        def get_glob_pattern(self):
            return "SST_%(depth:fmt=.1f)_%(Y)%(m)%(d).nc"

This plugin has several advantages over a simple glob pattern. Its filename
pattern can define parameters with specific formatting. Thus it can "fix" some
parameters and restrict its search. With the same example as above we can
select only the files for a specific depth::

    MyDataManager(depth=10.0).get_source()

If we fix all parameters we can also generate a filename for a given set of
parameters::

    MyDataManager(depth=10.0).get_filename(Y=2015, m=5, d=1)
    # or equivalent:
    MyDataManager(depth=10.0, Y=2015, m=5, d=1).get_filename()

See the `filefinder <https://filefinder.readthedocs.io/en/latest/>`__
documentation for more details on its features.

Loading and writing data
========================

When loading data, the end goal is typically to overwrite
:meth:`.DataManagerBase.get_data`, to adapt for different libraries to use,
data formats, etc. Plugins can inherit from :class:`.LoaderPluginAbstract`.
This abstract plugin implement ``get_data`` to include postprocessing.
If a method :meth:`~.LoaderPluginAbstract.postprocess_data` is defined on the
data manager (and it does not raise a ``NotImplementedError``), it will
automatically be run on loaded data. This can be bypassed by passing
``ignore_postprocess=True`` to ``get_data()``.
The abstract plugin relies on :meth:`~.LoaderPluginAbstract.load_data_concrete`
to actually load the data. This method can be implemented in different plugins
dealing with different libraries, formats, etc.

On the other end, plugins to write data to a store (to disk or on a remote data
store) inherict from :class:`.WriterPluginAbstract`. This abstract plugin define
the :meth:`~.WriterPluginAbstract.write` method. Subclasses are expected to
implement it. It implements a method to retrieve metadata that can be added to
the data stored if possible.

.. note::

    By default, this metadata includes the parameters of the data manager, the
    current running script, the date, and if the script is part of a git project
    the last commit hash of that project.

    Additional metadata could be included. Planned future additions are more
    details on the current state of the git project (diff to HEAD for instance).

The writing of data is formalized as the execution of "writing calls". Each call
consist of data (array, dataset,...) to write to a target (file,
data-store,...). The ``write`` function a plugin can call to more specialized
functions that act on calls. The simplest would be
:meth:`.WriterPluginAbstract.send_single_call`, but more complex one can be used
like :meth:`.WriterPluginAbstract.send_calls` that send multiple calls serially
or :meth:`.XarrayMultiFileWriterPlugin.send_calls_together` that can send
multiple calls in parallel using Dask.

The library actually writing the data may fail if the containing directories do
not already exist. To this end, the methods
:meth:`~.WriterPluginAbstract.check_directory` and
:meth:`~.WriterPluginAbstract.check_directories` will check that the
directory or directories containing the call(s) target(s) exist, and if not
create them. The ``write()`` method may automatically call them, depending on
the plugin implementation.

Some data may be generated quickly but could still benefit from being
saved/cached on disk. The plugin :class:`.CachedWriterPlugin` will call its
method :meth:`~.CachedWriterPlugin.generate_data` if the source file does not
exists.


Xarray
======

A compilation of plugin for interfacing with `Xarray
<https://xarray.pydata.org/>`__ is available in
:mod:`data_assistant.data.xarray`. This submodule is not imported in the top
level package to avoid importing Xarray unless needed.

To load data,:class:`.XarrayFileLoaderPlugin` will load from a single file or
store with :external+xarray:func:`~xarray.open_dataset` and
:class:`.XarrayMultiFileLoaderPlugin` from multiple files using
:external+xarray:func:`~xarray.open_mfdataset`.

To write data to a single file or store, use :class:`.XarrayWriterPlugin`. It
will guess to function to use from the file extension. It currently supports
Zarr and Netcdf.

.. note::

   The ``write()`` method will automatically add metadata to the dataset
   attributes via ``.XarrayWriterPlugin.set_metadata``. This is true for the
   other writer plugins below.

For data that is to be written across multiple files or stores, the plugin
:class:`.XarrayMultiFileWriterPlugin` will execute several writing calls either
one after the other, or in parallel. If given a :class:`Dask
client<distributed.Client>` argument,
:meth:`~.XarrayMultiFileWriterPlugin.write` will use
:meth:`~.XarrayMultiFileWriterPlugin.send_calls_together` to execute multiple
writing operations in parallel.

.. important::

    Doing so is not so straightforward. It may fail on some filesystems with
    permisssion errors. Using the scratch filesystem on a cluster might solve
    this issue. See :meth:`~.XarrayMultiFileWriterPlugin.send_calls_together`
    documentation for details on the implementation.

The :class:`.XarrayMultiFileWriterPlugin` plugin needs multiple datasets and
their respective target file. :class:`.XarraySplitWriterPlugin` intends to
simplify further the writing process by splitting automatically a dataset across
files. It must be paired with a source-managing plugin that implements the
:class:`.Splitable` protocol. Which means that some parameters can be left
unspecified and along which the dataset will be split. It must also be able to
return a filename given values for those unspecified parameters. The
:class:`.FileFinderPlugin` can be used to that purpose. For instance we can
split a dataset along its depth dimension and automatically group by month,
using a dataset along the lines of::

    >>> ds
    <xarray.Dataset>
    Dimensions:              (time: 365, depth: 50, lat: 4320, lon: 8640)
    Coordinates:
    * time                 (time) datetime64[ns] 2020-01-01 ... 2020-12-31
    * depth                (depth) int64 0 1 5 10 20 40 ... 500 750 1000
    * lat                  (lat) float32 89.98 89.94 89.9 ... -89.9 -89.94 -89.98
    * lon                  (lon) float32 -180.0 -179.9 -179.9 ... 179.9 180.0
    Data variables:
        temp                  (time, depth, lat, lon) float32 dask.array<chunksize=(1, 1, 4320, 8640), meta=np.ndarray>


and a data manager defined as::

    class DataManager(XarraySplitWriterPlugin, FileFinderPlugin, DataManagerBase):

        def get_root_directory(self):
            return "/data/directory/"

        def get_filename_pattern(self):
            """Yearly folders, date as YYYYMM and depth as integer."""
            return "%(Y)/temp_%(Y)%(m)_depth_%(depth:fmt=d).nc"

by calling ``DataManager().write(ds)``. Note this will detect that the smallest
time parameter in the pattern is the month and split the dataset appropriately
using :external+xarray:meth:`xarray.Dataset.resample`. This can be specified
manually or avoided alltogether. See :meth:`.XarraySplitWriterPlugin.write`
documentation for details.

.. note::

    If the overall :meth:`~.XarraySplitWriterPlugin.write` implementation is not
    appropriate, it is possible to control more finely the splitting process by
    using :meth:`~.XarraySplitWriterPlugin.split_by_unfixed` and
    :meth:`~.XarraySplitWriterPlugin.split_by_time`. The "time" dimension and
    its related parameters are split
