

*****
Usage
*****

Each dataset is defined by creating a subclass of :class:`~.DataInterface`. The
class definition will contain information on:

- where the data is located: on disk or in a remote store
- how to load or write data: with which library and function, how to
  post-process it, etc.

The interface can then be re-used in different scripts so that eventually, you
can get your data with two simple lines::

  >>> di = MyDataInterface()
  >>> di.get_data()

Each *instance* of that subclass corresponds to a set of parameters that can be
used to change aspects of the interface on the fly: choose only files for a
specific year, change the method to open data, etc.

.. _module-system:

Module system
=============

Features of the interface are split into individual modules that can be swapped
or modified.
The default :class:`.DataInterface` has four modules. Each module has an
attribute where the module instance can be accessed, and an attribute where its
type can changed:

+------------+------------+------------------------------+-------------+
| Instance   | Definition | Class                        |  Function   |
| attribute  | attribute  |                              |             |
+============+============+==============================+=============+
| parameters | Parameters | :class:`.ParametersAbstract` | manage      |
|            |            |                              | parameters  |
+------------+------------+------------------------------+-------------+
| source     | Source     | :class:`.SourceAbstract`     | manage      |
|            |            |                              | data source |
+------------+------------+------------------------------+-------------+
| loader     | Loader     | :class:`.LoaderAbstract`     |  load data  |
+------------+------------+------------------------------+-------------+
| writer     | Writer     | :class:`.WriterAbstract`     | write data  |
+------------+------------+------------------------------+-------------+

To change a module, we only need to change the module type. It can be a simple
attribute change, or a class definition with the appropriate name, like so::

    class MyDataInterface(DataInterface):

        # simple attribute change
        Parameters = ParametersDict

        # or a more complex definition
        class Source(SimpleSource):

            def get_source(self):
                ...

    # we can then access the modules
    di = MyDataInterface()
    di.source.get_source()


.. tip::

    Every module can access its parent interface via :attr:`Module.di`.

Parameters
----------

The parameters of the interface are stored in the `Parameters` module. They are
given as argument to the interface on initialization.

Parameters can be stored in a simple dictionary, or using objects from the
:doc:`configuration</config/index>` part of Neba like a Section or Application.
See the :ref:`existing parameters modules<existing_params>`.

There are two ways to access parameters.

- you can use the methods of the parameters module which works like a dictionary:
  :meth:`~.ParametersAbstract.get`, :meth:`~.ParametersAbstract.set`,
  :meth:`~.ParametersAbstract.update`::

    >>> di.parameters["a"] = 0
    >>> di.parameters["a"]
    0
    >>> di.parameters.update(a=1, b=2)

  If a key is not defined, ``di.parameters[key]`` will raise KeyError, and
  ``di.parameters.get(key)`` will return None by default.

  This ensures that you can swap the parameters container without problems.

- Or you can access the parameters container directly at
  :attr:`di.parameters.direct<.ParametersAbstract.direct>`. This is useful
  if you use a :class:`.Section` as a container::

    di.parameters.direct.my_subsection.my_trait = 0

  But using ``di.parameters["my_subsection.my_trait"] = 0`` will still work!

Some modules use a cache that needs to be reset when parameters are changed.
Both ways of accessing parameters will void the cache appropriately.

.. note::

    This is done in two ways. The parameters module methods will simply call
    :meth:`.DataInterface.trigger_callbacks` after their operation. For direct
    access, the dictionary container has ``__setitem__`` patched, and Sections
    objects have an `observer event
    <https://traitlets.readthedocs.io/en/stable/using_traitlets.html#observe>`__
    added. Direct access will only void the cache if a new parameter is added,
    or if the new value is different from the old

.. important::

   This does not include in-place operations on mutable parameters::

     di.parameters["my_list"].append(1)
     di.parameters["my_dict"]["key"] = 1
     # or
     di.parameters.direct["my_list"].append(1)
     di.parameters.direct["my_dict"]["key"] = 1

   will **not** trigger a callback.


.. tip::

   The parameters module is accessible from any other module at
   :attr:`Module.parameters`.

It might be useful to quickly change parameters, eventually multiple times,
before returning to the initial set of parameters. To this end, the method
:meth:`.DataInterface.save_excursion` will return a context manager that will
save the initial parameters and restore them when exiting::

    di.parameters["p"] = 0

    with di.save_excursion():
        # we change parameters
        self.parameters["p"] = 2
        self.get_data()

    # we are back to di.parameters["p"] == 0

This is used by :meth:`.DataInterface.get_data_sets` that return data for
multiple sets of parameters, for instance to get specific dates::

    data = di.get_data_sets(
        [
            {"Y": 2020, "m": 1, "d": 15},
            {"Y": 2021, "m": 2, "d": 24},
            {"Y": 2022, "m": 6, "d": 2},
        ]
    )


.. _source_module:

Source
------

The ``Source`` module manages the location of data that will be read or written
by other modules. It could be files on disk, or the address of a remote
data-store. It allows to use :meth:`.DataInterface.get_source`, though other
modules will typically call it automatically when they need it.

See :ref:`existing source modules<existing_source>`.

Sometimes, you may have data split in different locations. To solve this, you
can combine multiple source modules into one by taking the union (or
intersection) of their results. Say you have data files in two locations with
different naming convention::

    /data1/<year>/data1_<year><month><day>.nc
    and
    /data2/data2_<year><dayofyear>.nc

We combine two :class:`.FileFinderSource` by taking the union::

    class MyDataInterface(DataInterface):

        class Source1(FileFinderSource):
            def get_root_directory(self):
                return "data1"

            def get_filename_pattern(self):
                return "%(Y)/data1_%(Y)%(m)%(d).nc"

        class Source2(FileFinderSource):
            def get_root_directory(self):
                return "data2"

            def get_filename_pattern(self):
                return "data2_%(Y)%(j).nc"

        Source = SourceUnion.create([Source1, Source2])

If we need to run a method on one of the source modules, for instance to
generate a filename, we can specify a function to automatically select one
module. That function receives the instance of the module mix and should return
the class name of one base module. Let's say our first dataset contains years up
to 2010, and the second one the years after that.::

    class MyDataInterface(DataInterface):

        ...

        @staticmethod
        def _select_source(mod: SourceBase, **kwargs):
            year = mod.parameters.get("Y", None)
            # if user specify a year in kwargs it gets precedence
            year = kwargs.get("Y", year)
            if year is None:
                raise ValueError("Year not fixed")
            if year <= 2010:
                return "Source1"
            else:
                return "Source2"

        Source = SourceUnion.create([Source1, Source2], select=_select_source)

We can then run a method on a selected module with
``di.source.apply_select("get_filename", year=2015)``, we can specify the year
by hand or the year in the interface parameters will be used.

.. tip::

   The module mix will also try to dispatch any attribute access to the selected
   base module, so ``di.source.get_filename()`` will work.

More details on :ref:`module_mixes`.

Loader
------

The ``Loader`` module loads the data from the location specified by the Source
module using different libraries or functions. It allows to use
:meth:`.DataInterface.get_data`. The source can always be specified manually
with ``di.get_data(source="my_file")``. It also allows to post-process your
data, *ie* run a function every time it is loaded. For instance say we need to
change units on a variable, we just need to implement the
:meth:`~.LoaderAbstract.postprocess` method::

    class MyDataInterface(DataInterface):

        class Loader(XarrayLoader):
            def postprocess(self, data: xr.Dataset) -> xr.Dataset:
                # go from Kelvin to Celsius
                data["sst"] += 273.15
                return data

Now, every time we load data (using :meth:`.DataInterface.get_data`), the
function is applied. You can always disable it by passing
``di.get_data(ignore_postprocess=True)``.

New loaders should implement the method
:meth:`~.LoaderAbstract.load_data_concrete` that loads data from a given source.
:meth:`.LoaderAbstract.get_data` will deal with getting the source and applying
post-processing.

Writer
------

The Writer writes data to the location given by the Source module. It allows to
use :meth:`.DataInterface.write`.

The writer will create directories if needed, and can also add metadata to the
data you are writing:

* ``written_with_interface``: name of the interface class.
* ``created_by``: hostname and filename of the python script used
* ``created_with_params``: a string representing the parameters,
* ``created_on``: date of creation
* ``created_at_commit``: if found, the HEAD commit hash.
* ``git_diff_short``: if workdir is dirty, a list of modified files
* ``git_diff_long``: if workdir is dirty, the full diff (truncated) at
  :attr:`~.WriterAbstract.metadata_max_diff_lines`.

The writer will generate one or more *calls*, each consisting of a location and
data to write there. It will then execute calls serially or in parallel (for
instance when using Xarray and Dask).

Some writers are able to split your dataset into multiple files. They should
inherit :class:`.SplitWriterMixin`, and the source module should follow the
:class:`.Splitable` protocol.


.. _interface-typing:

Typing
------

Modules may deal with different types of parameters, source and data. Module
classes specify their supported types as generics, so you can check their base
class to see what input/output they support. For instance,
:class:`.XarrayLoader` can receive :class:`str` | :class:`os.PathLike` and
returns :class:`xarray.Dataset`.

However, since one of the use of Neba is to ease the management of multi-file
datasets, all modules are to be expected to receive either one source file, or
a list of them. ``XarrayLoader`` may receive a ``str`` or list thereof (that it
will concatenate into a single output).

The types of parameters, source, and data are also left as generics for the
interface class (in this order). By specifying them you get type-checks for some
top-level methods like :meth:`.DataInterface.get_data` or
:meth:`.DataInterface.get_source`, and because those generics are transmitted to
modules, it also allows to type-check compatibility between modules.

::

    class MyDataInterface(DataInterface[App, str, xr.Dataset]):
        Parameters = ParametersApp
        Source = FileFinderSource
        Loader = XarrayLoader

        # module instances must be type-hinted by hand :(
        parameters: ParametersApp[App]
        source: FileFinderSource
        Loader: XarrayLoader


.. note::

    Module having union types can be tricky. You can think about it in terms of
    inputs and outputs:

    - source modules output source,
    - loader modules take in source and output data,
    - writer modules take in source and data.

    For outputs, you should specify all types in your interface generic. For
    inputs, it's okay not to list them all.

    For example, if your source modules returns ``str | bytes`` you should list
    them all. That way, if your loader modules only takes in ``str`` as source,
    your type-checker should complain (since the loader might receive
    ``bytes``). And if your writer takes in ``str | bytes | os.PathLike``, you
    don't need to list ``os.PathLike``, since the source module will never
    return that.

.. _module_mixes:

Module mixes
============

Modules can be compounded together in some cases. The common API for this is
contained in :class:`.ModuleMix`. This generates a module with multiple 'base
modules'. It will instantiate and initialize all modules and store them in
:attr:`.ModuleMix.base_modules`.
Mix classes should be created with the class method :meth:`~.ModuleMix.create`.

This is used for instance to obtain the :class:`union<.SourceUnion>` or
:class:`intersection<.SourceIntersection>` of source files obtained by different
source modules. Or it could be used to write to multiple file format at once
(with different base writers).

Mixes can run methods on their base modules:

* :meth:`~.ModuleMix.apply_all` will run on **all** the base modules of the mix
  and return a list of outputs.
* :meth:`~.ModuleMix.apply_select` will only run on a **single** module. It will
  be selected by a user defined function that can be set in
  :meth:`~.ModuleMix.create` or with :meth:`.ModuleMix.set_select`. It chooses
  the appropriate base module based on the current state of the mix module, the
  interface parameters, and eventual keywords arguments it might receive. It
  should return the class name of one of the module.
* :meth:`~.ModuleMix.apply` will use the *all* or *select* version based on the
  value of the ``all`` argument. In all methods, *args* and *kwargs* are passed
  to the method that is run, and the *select* keyword argument is a passed to
  the selection function.

.. tip::

    If an attribute access fails on a ModuleMix, it tries to select a base
    module and access that attribute on it. This allows to dispatch quickly to a
    base module.

.. _cache-module:

Cache module
============

.. note::

   This section is aimed at module writers. Users can safely ignore it.

It might help for some modules to have a cache to write information into. For
instance source modules for multiple files leverage this. A module simply needs
to be a subclass of :class:`.CachedModule`. This will automatically create a
``cache`` attribute containing a dictionary. It will also add a callback to the
list of reset-callbacks of the interface, so that this module cache will be
voided on parameters change. This can be disabled however by setting the class
attribute ``_add_void_callback`` to False (in the new module subclass).

If a module has a cache, you can use the :func:`.autocached` decorator to make
the value of one of its method or property automatically cached. Watch out
for the order of decorators for properties::

    class SubModule(SourceAbstract, CachedModule):

        @property
        @autocached
        def something(self):
            ...

Defining new modules
====================

Users will typically only need to use existing modules, possibly redefining some
of their methods, but in the case more dramatic changes are necessary, here are
more details on the module system.

All modules inherit from abstract classes that define their API. Note that they
are not defined through the :external+python:mod:`abc` module, and thus will not
raise if methods lack an implementation. These classes are more guidelines than
strict protocols.

.. admonition:: For developers

    Nevertheless it is advised to keep a common signature for module subclasses,
    relying on keyword arguments if necessary. This helps ensure
    inter-operability between modules and easy substitution of module types.

To add more modules types, the correspondence between the attribute containing
the module instance and the one containing the module type must be indicated in
the mapping :attr:`~.DataInterface._modules_attributes`.

.. note::

   The parameters module is instantiated first. Other modules are instantiated
   in the order of that mapping. Modules are then setup in the same order.

Interfaces are initialized with an optional argument giving the parameters, and
additional keyword arguments. All modules are instantiated with the same
arguments. Their :attr:`~.Module.di` attribute is set to the parent interface.
Once they are all instantiated, they are setup using the :meth:`.Module.setup`
method. This allow to be (mostly) sure that all other module exist if there is
need for interplay.

.. note::

   'Mostly' because if a module fails to instantiate and its attribute
   :attr:`.Module._allow_instantiation_failure` is True, it will only log a
   warning and the module will not be accessible.

For the most part, modules are made to be independent of each others, but it can
be useful to have interplay. The interface provides some basic API that modules
can leverage like :meth:`.DataInterface.get_source` or
:meth:`.DataInterface.get_data`. See :doc:`existing_modules` for examples.

Interface store
===============

To help deal with numerous interfaces classes, we provide a
:class:`mapping<.DataInterfaceStore>` allowing to store and easily access your
interfaces using their :attr:`~.DataInterface.ID` or
:attr:`~.DataInterface.SHORTNAME` attributes, or a custom name.

::

    from neba.data import DataInterface, DataInterfaceStore

    class MyDataInterface(DataInterface):
        ID = "SomeLongID"
        SHORTNAME = "SST"

    store = DataInterfaceStore(MyDataInterface)

    di_cls = store["SomeLongID"]
    # or
    di_cls = store["SST"]

If multiple interface0 have the same shortname, they can only be accessed by
their ID. Trying to access with an ambiguous shortname will raise a KeyError.

You can directly register an interface with a decorator::

    store = DataInterfaceStore()

    @store.register()
    class MyDataInterface(DataInterface):
        ...

You can also store an interface as an import string. When accessed, the store
will automatically import your interface (and replace the string by the imported
class for subsequent accesses).::

    store.add("path.to.MyDataInterface")
    di_cls = store["MyDataInterface"]
    # an interface class
