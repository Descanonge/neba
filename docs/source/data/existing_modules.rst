
****************
Existing modules
****************

The interface class is expected to be populated by modules (see
:ref:`module-system`). Here is a quick description of modules that are already
defined in Neba.


.. _existing_params:

Parameters
==========

.. currentmodule:: neba.data.params

.. autosummary::
   :nosignatures:

    ParametersDict
    ParametersSection
    ParametersApp

Dict
----

:class:`.ParametersDict` stores the parameters in a dictionary. Technically it
is a subclass of dict that has a callback setup to void the modules cache when a
parameter is changed.

The callback is called only when setting a value that is new or different from
the old value. Any change to a mutable (list or dict) will not register::

    # Will void cache
    di.parameters.direc["a"] = 0
    di.parameters.direct["nested"] = {"b": 1}

    # Will *not* void cache
    di.parameters.direct["a"] = 0  # no change
    di.parameters.direct["nested"]["b"] = 2  # mutable operation


Section
-------

:class:`.ParametersSection` stores the parameters in a :class:`.Section` object.
The section class is specified in the attribute
:attr:`~.ParametersSection.SECTION_CLS` and defaults to an empty Section. When
initialized, the module creates a new ``SECTION_CLS`` and updates it with the
arguments passed to it.

It can be defined with::

    class MyDataInterface(DataInterface):

        Parameters = ParametersSection.new(MySection)

The section has a callback setup to it so that any modification will trigger a
cache void (except mutable modification)::

    # Will void cache
    di.parameters.direct["a"] = 0
    di.parameters.direct.a = 1
    di.parameters.direct.nested.b = 1
    di.parameters.direct["my_list"] = [0]

    # Will *not* void cache
    di.parameters.direct["a"] = 1  # no change
    di.parameters.direct["my_list"].append(1)  # mutable operation


App
---

:class:`.ParametersApp` stores its parameters in an :class:`.Application`
object. An application *must* be supplied as argument. It will be **copied**
(any modification of the interface parameters will not affect the original
application instance).

.. tip::

    The specific application class does not need to be specified, but can be
    type-hinted with::

        from neba.data.util import T_Source, T_Data

        class MyDataInterface(DataInterface[MyApp, T_Source, T_Data]):
            ...

    ``T_Source`` and ``T_Data`` can also be specified, see
    :ref:`interface-typing`.


.. _existing_source:

Source
======

.. currentmodule:: neba.data.source

.. autosummary::
   :nosignatures:

    SimpleSource
    GlobSource
    FileFinderSource

Simple
------

For simple case, :class:`.SimpleSource` will just return its attribute
:attr:`~.SimpleSource.source_loc`::

    class MyDataInterface(DataInterface):
        Source = SimpleSource
        Source.source_loc = "/my_data/file.txt"

MultiFile
---------

For datasets consisting of multiple files the package provide two modules that
follow the abstract class :class:`.MultiFileSource`. For both of them the user
should implement :meth:`~.MultiFileSource.get_root_directory` which returns the
directory containing the files (as a path, or a list of sub-folders that will be
joined).

Glob
++++

The module :class:`.GlobSource` can find files on disk that follow a pattern
defined by :meth:`~.GlobSource.get_glob_pattern`, using :mod:`glob`. Files on
disk matching the pattern are cached and available at
:meth:`~.GlobSource.datafiles`. For instance::

    class MyDataInterface(DataInterface):

        class Source(GlobSource):
            def get_root_directory(self):
                return ["/data", self.parameters["user"], "subfolder"]

            def get_glob_pattern(self):
                return "SST_*.nc"

    files = MyDataInterface().get_source()

FileFinder
++++++++++

For a similar scenario of a dataset split across many files (for different
dates, variables or parameters values) an even more precise solution is provided
by :class:`.FileFinderSource`. This module relies on the `filefinder
<https://filefinder.readthedocs.io/en/latest/>`__ package to find files
according to a specific filename pattern. For instance::

    class MyDataInterface(DataInterface):

        class Source(FileFinderSource):
            def get_root_directory(self):
                return ["/data", self.parameters["user"], "subfolder"]

            def get_glob_pattern(self):
                return "SST_%(depth:fmt=.1f)_%(Y)%(m)%(d).nc"

This module has several advantages over a simple glob pattern. Its filename
pattern can define parameters with specific formatting. Thus it can "fix" some
parameters and restrict its search. With the same example as above we can
select only the files for a specific depth::

    MyDataInterface(depth=10.0).get_source()

If we fix all parameters we can also generate a filename for a given set of
parameters::

    MyDataInterface(depth=10.0).source.get_filename(Y=2015, m=5, d=1)
    # or equivalent:
    MyDataInterface(depth=10.0, Y=2015, m=5, d=1).source.get_filename()

See the `filefinder <https://filefinder.readthedocs.io/en/latest/>`__
documentation for more details on its features.


Xarray
======

A compilation of modules for using `Xarray <https://xarray.pydata.org/>`__ is
available in :mod:`neba.data.xarray`. This submodule is not imported in the top
level package to avoid importing Xarray unless needed.

.. currentmodule:: neba.data.xarray

.. autosummary::
   :nosignatures:

    XarrayLoader
    XarrayWriter
    XarraySplitWriter

Loaders
-------

:class:`.XarrayLoader` will load either from a single file or store with
:external+xarray:func:`~xarray.open_dataset` or from multiple files using
:external+xarray:func:`~xarray.open_mfdataset`.

Options for these functions can be changed in the attributes
:attr:`~.XarrayLoader.open_dataset_kwargs` and
:attr:`~.XarrayLoader.open_mfdataset_kwargs`::

    class MyDataInterface(DataInterface):
        class Loader(XarrayLoader):
            open_mfdataset_kwargs = dict(...)

Writers
-------

:class:`.XarrayWriter` allows to write to either a single file/store or multiple
files if given a sequence of datasets. It will guess the function to use from
the file extension. It currently supports Zarr and Netcdf.

.. note::

   The ``write()`` method will automatically add metadata to the dataset
   attributes via :meth:`~.XarrayWriter.add_metadata`.

When writing data across multiple files or stores, if given a :class:`Dask
client<distributed.Client>` argument, it will use
:meth:`~.XarrayWriter.send_calls_together` to execute multiple writing
operations in parallel.

.. important::

    Doing so is not so straightforward. It may return permission errors on some
    filesystems. Using the scratch filesystem on a cluster might solve this
    issue. See :meth:`~.XarrayWriter.send_calls_together` documentation for
    details on the implementation.

When writing to multiple files, the :class:`.XarrayWriter` module needs multiple
datasets and their respective target file. :class:`.XarraySplitWriter` intends
to simplify further the writing process by splitting automatically a dataset
across files. It must be paired with a source module that implements the
:class:`.Splitable` protocol. Which means that some parameters can be left
unspecified along which the dataset will be split. It must also be able to
return a filename given values for those unspecified parameters. The
:class:`.FileFinderSource` can be used to that purpose. For instance we can
split a dataset along its depth dimension and automatically group by month,
using data along the lines of::

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


and an interface defined as::

    class MyDataInterface(DataInterface):

        Writer = XarraySplitWriter

        class Source(FileFinderSource):
            def get_root_directory(self):
                return "/data/directory/"

            def get_filename_pattern(self):
                """Yearly folders, date as YYYYMM and depth as integer."""
                return "%(Y)/temp_%(Y)%(m)_depth_%(depth:fmt=d).nc"

we can then simply call ``MyDataInterface().write(ds)``. Note this will detect
that the smallest time parameter in the filename pattern is the month and split
the dataset appropriately using :external+xarray:meth:`xarray.Dataset.resample`.
This can be specified manually or avoided altogether. See the
:meth:`.XarraySplitWriter.write` documentation for details.

.. note::

    If the overall :meth:`~.XarraySplitWriter.write` implementation is not
    appropriate, it is possible to control more finely the splitting process by
    using :meth:`~.XarraySplitWriter.split_by_unfixed` and
    :meth:`~.XarraySplitWriter.split_by_time`. The "time" dimension is split
    separately to account for the fact that a filename pattern will define
    separate datetime elements (the year, the month, the day, ...).
