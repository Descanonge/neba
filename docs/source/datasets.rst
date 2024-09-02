
.. currentmodule:: data_assistant.data

******************
Dataset management
******************

This package has a submodule :mod:`~data_assistant.data` to ease the creation
and management of multiple dataset with different file format, structure, etc.
that can all depend on various parameters. Each new dataset is specified by
creating a new subclass of :class:`~.DataManagerBase`. It possess different
*modules* that each cover some functionality:

* :class:`params_manager<.ParamsManagerAbstract>` manages the parameters of the
  dataset. The :class:`default<.ParamsManager>` uses a simple dictionary.
* :class:`source<.SourceAbstract>` finds and manages the data sources: files,
  data stores, remote resources, etc.
* :class:`loader<.LoaderAbstract>` loads data from these sources into python,
  using a given library
* :class:`writer<.WriterAbstract>` writes data to a source (to disk or other)

The class of each module can be changed to fit the need of each dataset. More
modules can also be added easily to cover more specific features. Only the
parameters module is necessary, all others are optional and can be left to their
abstract class.

If each subclass of DataManager is associated to a specific dataset, each
*instance* of that subclass corresponds to a set of parameters that can be used
to change aspects of the dataset on the fly: choose only files for a specific
year, change the method to open data, etc.

.. _module-system:

Module system
=============

This framework tries to make those data managers objects as universal as
reasonably possible. The base class does not specify a data source (it could be
one file, multiple files, a remote datastore, ...) or a data type.

Definition in the data manager
------------------------------

Each :class:`module<.Module>` defines itself how (and especially where) it can
be added to a data manager. This is thanks to two important class attributes:

* ``_INSTANCE_ATTR`` gives at which attribute name the module will be kept in
  the data manager, for instance for source modules, it is ``"source"``.
* ``_TYPE_ATTR`` gives at which attribute name the *type* of the module will be
  kept at. It makes it easy to subclass data-managers:
  ``SomeDataManager._Source`` will give the type of the source module of
  SomeDataManager.

During the definition of a data manager class, it will look for *any* attribute
that defines a subclass of :class:`.Module`. It can even just be a nested class
definition. It will register the types of module found. This allows quick
definition of data managers with subclasses of different modules. For example,
we don't need to do do anything more that::

    class DataManagerProjet(DataManagerBase):
        """Define a data-manager base for the project."""

        _Source = SimpleSource
        _Loader = XarrayLoader

    class SST(DataManagerProject):

        class Source(DataManagerProject._Source):
            """This class name does not matter."""

            def get_source(self):
                ...

        class Loader(DataManagerProject._Loader):
            def postprocess_data(self, data):
                ...

.. note::

    Only one module of each type will be kept in the data manager. Later
    definitions will overwrite the previous ones. However if one is defined
    through its designated type attribute (example:
    ``_Source = MySourceSubClass``), it will keep priority.

.. note::

   Because of the dynamic nature of these class definition
   (:class:`.DataManagerBase` uses ``__init_subclass__`` which is similar to
   using a custom metaclass or a class decorator) a static type checker will be
   lost. You can still get around it by naming your classes with the
   corresponding module type attribute (*_Source*, *_Loader*, etc.) so that a
   static type checker will not complain at using ``DataManagerProject._Source``
   as a base class. And you can add a type hint to the instance attribute, such
   as ``loader: _Loader``.

   A mypy plugin might be added to do this automatically.


Defining new modules
--------------------

Dataset managers are initialized with an optional argument giving the
parameters, and additional keyword arguments. All modules are instanciated with
the same arguments. Immediately after, their :attr:`~.Module.dm` attribute is
set to the containing data manager. Once they are all instanciated, they are
initialized using the :meth:`.Module._init_module` method. This allow to be
(mostly) sure that all other module exist if there is need for interplay.

.. note::

   *Mostly* because if a module fails to instanciate it will only log a warning,
   and thus will not be accessible.

The ``_init_module()`` method is planned for inheritance cooperation. Each new
subclass should make a ``super()._init_module()`` call whenever appropriate. But
the data manager initialization (:class:`.HasModules._init_modules`) will make
sure every class in the MRO is initialized. So for instance in
``class NewModule(SubModuleA, SubModuleB)`` both ``SubModuleA._init_module`` and
``SubModuleB._init_module`` will be called, even though they don't necessarily
know about each other.

.. important::

   All modules have easy access to the data-manager parameters by using
   :meth:`~.Module.params`.

For the most part, modules are made to be independant of each others, but it can
be useful to have interplay. The data-manager provides some basic API that
plugins can leverage like :meth:`.DataManagerBase.get_source` or
:meth:`.DataManagerBase.get_data`. For more specific features the package
contains some abstract base classes that define the methods to be expected: for
instance :class:`loader.LoaderAbstract`, :class:`writer.WriterAbstract`. See
:doc:`existing_modules` for a list of available plugins.
See :class:`.SplitWriterMixin` for an example of interplay facilitator and the
implementation of :class:`.XarraySplitWriter` that has multiple submodules
parents as discussed in the paragraph above.


Dataset parameters
==================

A dataset instance is supposed to represent a specific set of parameters.
Changing parameters might affect modules, and thus it is recommended to change
parameters using :meth:`.DataManagerBase.set_params` or
:meth:`.DataManagerBase.update_params`. After the parameters have been modified,
this function will launch all "reset callbacks" that have been registered by
modules. For instance, some modules may use a cache and need to void it after a
parameters change.

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

As noted above, how parameters are stored and managed can be customized. The
default is a simple dictionnary storing the parameters: :class:`.ParamsManager`.
The package also provides :class:`.ParamsManagerScheme` where parameters are
stored in a :class:`data_assistant.config.scheme.Scheme` object. By specifying
the exact expected type of the parameters, this can ensure the existence of
parameters::

    class MyParameters(Scheme):
        threshold = Float(0.5)

    class Dataset(ParamsSchemePlugin, DataManagerBase):

        params: MyParameters

Now we are sure that ``Dataset().params`` will contain a ``threshold``
attribute. This comes at the cost of flexibility since schemes are not as
malleable as other mutable mapping types as it only implements
:meth:`~.Scheme.update` (see :ref:`mapping-interface`).

.. note::

   The abstract parameters module is expecting that the parameters are storred
   in a :class:`~collections.abc.MutableMapping`. The Scheme class implements
   *most* of what is needed to be mutable, but cannot delete keys.

.. _cache-module:

Cache module
============

.. note::

   This section is aimed at module writers. Users can safely ignore it.

It might help for some modules to have a cache to write information into. For
instance plugins managing source consisting of multiple files leverage this.
A module simply need to be a subclass of :class:`.CachedModule`. This will
automatically create a *cache* attribute containing a dictionnary. It will also
add a callback to the list of reset-callbacks of the data manager, so that this
module cache will be voided on parameters change. This can be disable however
by setting the class attribute ``_add_void_callback`` to False (in the new
submodule class).

If a module has a cache, you can use the :func:`.autocached` decorator to make
the value of one of its property automatically cached::

    class SubModule(CachedModule):

        @property
        @autocached
        def something(self):
            ...


Module mixes
============

Modules can be compounded together in some cases. The common API for this is
contained in :class:`.ModuleMix`. This generates a module with multiple 'base
modules'. It will instanciate and initialize all modules and store them in
:attr:`.ModuleMix.base_modules`.

This is used for instance to obtain the :class:`union<.SourceUnion>` or
:class:`intersection<.SourceIntersection>` of source files obtained by different
source modules.

Mixes class should be created with the class method :meth:`~.ModuleMix.create`.
For instance with::

    _Source = SourceUnion.create([SourceOne, SourceTwo])

we will obtain files catched by *SourceOne* and *SourceTwo* (without overlap) when
calling ``data_manager.get_source()``.
