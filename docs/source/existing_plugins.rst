
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

check_directories

Automatically generate and save data if the source does not exist.
:class:`.CachedWriterPlugin`
generate_data


Xarray
======

Everything is in :mod:`data_assistant.data.xarray`. Xarray not imported
otherwise (sort of lazy loading).

Load from single file/store.
:class:`.XarrayFileLoaderPlugin`
Load from multiple files.
:class:`.XarrayMultiFileLoaderPlugin`

Write to a single file/store.
:class:`.XarrayWriterPlugin`
seng_single_call guess the format from filename. Use Zarr or Netcdf
corresponding function.
set_metadata

Write to multiple files in parallel (or series).
:class:`.XarrayMultiFileWriterPlugin`
with send_calls_together (redefine write to use this)
under the hood use dask (if given a client)
difficulties of doing this. Some filesystems might not work (use scratch!)

Split a single dataset across multiple files automatically!
It is meant to work with :class:`.FileFinderPlugin`, but it could be paired
with any source plugin that implements the :class:`.HasUnfixed` protocol.
:class:`.XarraySplitWriterPlugin`
