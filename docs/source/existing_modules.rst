
.. currentmodule:: data_assistant

****************
Existing modules
****************

The *Dataset* class is expected to be populated by modules (see
:ref:`module-system`). Here is a quick description of modules that are bundled
with this package.

The features managed by the modules presented below inherit from abstract
classes that define the API for that feature. Note that they are not defined
through the :external+python:mod:`abc` module, and thus will not raise if
instantiated. These classes are more guidelines than strict protocols.

.. note:: For developers

    Nevertheless it is advised to keep a common signature for module subclasses,
    relying on keyword arguments if necessary. This helps ensure
    inter-operability between module and easy substitution of modules types.

Parameters
==========

The first module manages the parameters of the Dataset instance. There is an
abstract class :class:`.ParamsManagerAbstract`, but the base Dataset class
sets its parameters module to :class:`.ParamsManager` by default (which use a
simple dictionnary for storing parameters).

A :class:`.Section` can be used to store parameters using
:class:`.ParamsManagerSection`. It allows to use the parameters retrieval from
:doc:`configuration<configuration>`, and restrict parameters to those statically
defined. Parameters can be added to the section at runtime though with
:meth:`.Section.add_trait` or :meth:`.Section.update`. The section to use must
be specified as a class attribute::

    class Parameters(Section):
        ...

    class MyDataset(Dataset):

        class _Params(ParamsManagerSection):
            SECTION_CLS = Parameters

Similarly, :class:`.ParamsManagerApp` will store parameters in a section object,
whose parameters are obtained from a global, shared :class:`.ApplicationBase`
instance. The dataset must be registered befored using
:meth:`.ApplicationBase.register_orphan`. At the dataset instantiation, the
dataset traits (if any have been defined) will be obtained from the application
orphan sections, and the parameters module will copy the application.

::

    class MyApp(ApplicationBase):
        ...

    @MyApp.register_orphan()
    class MyDataset(Dataset):

        # eventually, dataset specific traits
        data_dir = Unicode("/data")

        _Params = ParamsManagerApp

    # simply need to create a new instance
    ds = MyDataset()

In the example above, instanciating will retrieve a global instance of MyApp
(creating one if necessary). The '*data_dir*' trait is configurable (in
configuration file or command line) with the key '*MyDataset.data_dir*' and its
value will be retrieved automatically. All traits defined in MyApp and whose
value is obtained from configuration files and command line will be copied to
the parameters module, and available in a MyApp copy.

.. note::

   The parameters are copied, changing the shared MyApp instance will not affect
   the dataset after creation.


Source
======

The data is found from a source: one or more files on disk, or a remote
data-store for instance.

For simple case which do not need a full method, :class:`.SimpleSource` will
simply return its attribute :attr:`~.SimpleSource.source_loc`. It could also be
sufficient to simply rewrite :meth:`~.SourceAbstract.get_source`.

For datasets consisting of multiple files the package provide two modules that
follow :class:`.MultiFileSource`. For both of them the user should implement
:meth:`~.MultiFileSource.get_root_directory` which returns the directory
containing the files (as a path, or a list of sub-folders that will be joined).

The module :class:`.GlobSource` can find files on disk that follow a given
pattern, defined by :meth:`~.GlobSource.get_glob_pattern`. Files on disk
matching the pattern are cached and available at :meth:`~.GlobSource.datafiles`.
For instance::

    class MyDataManager(DataManagerBase):

        class Source(GlobSource):
            def get_root_directory(self):
                return ["/data", self.params["user"], "subfolder"]

            def get_glob_pattern(self):
                return "SST_*.nc"

    files = MyDataManager().get_source()

For a similar scenario of a dataset across many files (for different dates,
variables or parameters values) an even more precise solution is provided with
:class:`.FileFinderSource`. This module relies on the `filefinder
<https://filefinder.readthedocs.io/en/latest/>`__ package to find files
according to a specific filename pattern. For instance::

    class MyDataManager(DataManagerBase):

        class Source(FileFinderSource):
            def get_root_directory(self):
                return ["/data", self.params["user"], "subfolder"]

            def get_glob_pattern(self):
                return "SST_%(depth:fmt=.1f)_%(Y)%(m)%(d).nc"

This module has several advantages over a simple glob pattern. Its filename
pattern can define parameters with specific formatting. Thus it can "fix" some
parameters and restrict its search. With the same example as above we can
select only the files for a specific depth::

    MyDataManager(depth=10.0).get_source()

If we fix all parameters we can also generate a filename for a given set of
parameters::

    MyDataManager(depth=10.0).source.get_filename(Y=2015, m=5, d=1)
    # or equivalent:
    MyDataManager(depth=10.0, Y=2015, m=5, d=1).source.get_filename()

See the `filefinder <https://filefinder.readthedocs.io/en/latest/>`__
documentation for more details on its features.

Loading and writing data
========================

Modules loading data inherit from :class:`.LoaderAbstract`.
This abstract module implement ``get_data`` to include postprocessing.
If a method :meth:`~.LoaderAbstract.postprocess_data` is defined in the
module (and it does not raise a ``NotImplementedError``), it will
automatically be run on loaded data. This can be bypassed by passing
``ignore_postprocess=True`` to ``get_data()``.
The abstract module relies on :meth:`~.LoaderAbstract.load_data_concrete`
to actually load the data. This method can be implemented in different modules
dealing with different libraries, formats, etc.

On the other end, modules to write data to a store (to disk or on a remote data
store) inherict from :class:`.WriterAbstract`. This abstract module define
the :meth:`~.WriterAbstract.write` method. Subclasses are expected to
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
data-store,...). The ``write`` function a module can call to more specialized
functions that act on calls. The simplest would be
:meth:`.WriterAbstract.send_single_call`, but more complex one can be used like
:meth:`.WriterAbstract.send_calls` that send multiple calls serially or
:meth:`.XarrayMultiFileWriter.send_calls_together` that can send multiple calls
in parallel using Dask.

The library actually writing the data may fail if the containing directories do
not already exist. To this end, the methods
:meth:`~.WriterAbstract.check_directory` and
:meth:`~.WriterAbstract.check_directories` will check that the directory or
directories containing the call(s) target(s) exist, and if not create them. The
``write()`` method may automatically call them, depending on the module
implementation.

Some data may be generated quickly but could still benefit from being
saved/cached on disk. The module :class:`.CachedWriter` will call its
method :meth:`~.CachedWriter.generate_data` if the source file does not
exists.


Xarray
======

A compilation of module for interfacing with `Xarray
<https://xarray.pydata.org/>`__ is available in
:mod:`data_assistant.data.xarray`. This submodule is not imported in the top
level package to avoid importing Xarray unless needed.

To load data,:class:`.XarrayLoader` will load from a single file or store with
:external+xarray:func:`~xarray.open_dataset` and :class:`.XarrayMultiFileLoader`
from multiple files using :external+xarray:func:`~xarray.open_mfdataset`.

To write data to a single file or store, use :class:`.XarrayWriter`. It
will guess to function to use from the file extension. It currently supports
Zarr and Netcdf.

.. note::

   The ``write()`` method will automatically add metadata to the dataset
   attributes via ``.XarrayWriter.set_metadata``. This is true for the other
   writer modules below.

For data that is to be written across multiple files or stores, the module
:class:`.XarrayMultiFileWriter` will execute several writing calls either one
after the other, or in parallel. If given a :class:`Dask
client<distributed.Client>` argument, :meth:`~.XarrayMultiFileWriter.write` will
use :meth:`~.XarrayMultiFileWriter.send_calls_together` to execute multiple
writing operations in parallel.

.. important::

    Doing so is not so straightforward. It may fail on some filesystems with
    permisssion errors. Using the scratch filesystem on a cluster might solve
    this issue. See :meth:`~.XarrayMultiFileWriter.send_calls_together`
    documentation for details on the implementation.

The :class:`.XarrayMultiFileWriter` module needs multiple datasets and their
respective target file. :class:`.XarraySplitWriter` intends to simplify further
the writing process by splitting automatically a dataset across files. It must
be paired with a source-managing module that implements the :class:`.Splitable`
protocol. Which means that some parameters can be left unspecified and along
which the dataset will be split. It must also be able to return a filename given
values for those unspecified parameters. The :class:`.FileFinderSource` can be
used to that purpose. For instance we can split a dataset along its depth
dimension and automatically group by month, using a dataset along the lines of::

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

    class DataManager(XarraySplitWriterModule, FileFinderModule, DataManagerBase):

        def get_root_directory(self):
            return "/data/directory/"

        def get_filename_pattern(self):
            """Yearly folders, date as YYYYMM and depth as integer."""
            return "%(Y)/temp_%(Y)%(m)_depth_%(depth:fmt=d).nc"

by calling ``DataManager().write(ds)``. Note this will detect that the smallest
time parameter in the pattern is the month and split the dataset appropriately
using :external+xarray:meth:`xarray.Dataset.resample`. This can be specified
manually or avoided alltogether. See :meth:`.XarraySplitWriter.write`
documentation for details.

.. note::

    If the overall :meth:`~.XarraySplitWriter.write` implementation is not
    appropriate, it is possible to control more finely the splitting process by
    using :meth:`~.XarraySplitWriter.split_by_unfixed` and
    :meth:`~.XarraySplitWriter.split_by_time`. The "time" dimension and its
    related parameters are split
