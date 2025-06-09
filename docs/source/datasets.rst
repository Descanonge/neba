
.. currentmodule:: data_assistant.data

******************
Dataset management
******************

This package has a submodule :mod:`~data_assistant.data` to ease the creation
and management of multiple dataset with different file format, structure, etc.
that can all depend on various parameters. Each new dataset is specified by
creating a new subclass of :class:`~.Dataset`. It contains
interchangeable *modules* that each cover some functionalities.

If each Dataset subclass specifies access to some data, and each *instance* of
that subclass corresponds to a set of parameters that can be used to change
aspects of the dataset on the fly: choose only some files for a specific year,
change the method to open data, etc.

.. _module-system:

Module system
=============

This framework tries to make those data managers objects as universal as
reasonably possible. The base class does not specify a data source (it could be
one file, multiple files, a remote datastore, ...) or a data type (it could be
opened by different libraries).

Definition in the data manager
------------------------------

The default :class:`.Dataset` has four modules:

* ``params_manager`` defined at :class:`_Params<.ParamsManager>` to manage the
  data-manager parameters
* ``source`` defined at :class:`_Source<.SourceAbstract>` to manage the data
  source
* ``loader`` defined at :class:`_Loader<.LoaderAbstract>` to load data
* ``writer`` defined at :class:`_Writer<.WriterAbstract>` to write data

.. note::

    The parameter manager is the only one to not be abstract, being essential to
    the working of the data-manager. Like for the other modules, it can be
    changed to a subclass.

To change a module, we only need to change the module type contained in an
attribute. It is expected to be done in a Dataset subclass. It can be a simple
attribute change, or a class definition with the appropriate name, like so::

    # simple attribute changes
    class DataManagerProjet(Dataset):
        """Define a data-manager base for the project."""

        _Source = SimpleSource
        _Loader = XarrayLoader

    # more complex definitions
    class SST(DataManagerProject):

        class _Source(DataManagerProject._Source):

            def get_source(self):
                ...

        class _Loader(DataManagerProject._Loader):
            def postprocess_data(self, data):
                ...

Defining new modules
--------------------

Users will typically only need to use existing modules, possibly with
redefining some of its methods. In the case more dramatic changes are necessary,
here are more details on the module system.

The :class:`.Dataset` class inherits from :class:`.HasModules` that deals with
most of the module system. Modules must be registered in the
:attr:`.HasModules._registered_modules` attribute, which is a list of named
tuples each containing three key informations:

* the attribute name that will hold the module **instance**
* the attribute name that will hold the module **type** or definition
* the class of the module.

Dataset managers are initialized with an optional argument giving the
parameters, and additional keyword arguments. All modules are instantiated with
the same arguments. Immediately after, their :attr:`~.Module.dm` attribute is
set to the containing data manager. Once they are all instantiated, they are
initialized using the :meth:`.Module._init_module` method. This allow to be
(mostly) sure that all other module exist if there is need for interplay.

.. note::

   'Mostly' because if a module fails to instantiate it will only log a warning,
   and will not be accessible.

The :meth:`~.Module._init_module()` method is planned for inheritance
cooperation. Each new subclass should make a ``super()._init_module()`` call
whenever appropriate. The dataset initialization
(:meth:`.HasModules._init_modules`) will make sure every class in the MRO is
initialized. So for instance in ``class NewModule(SubModuleA, SubModuleB)`` both
``SubModuleA._init_module`` and ``SubModuleB._init_module`` will be called, even
though they don't necessarily know about each other.

.. important::

   All modules have easy access to the dateset parameters by using
   :meth:`~.Module.params`.

For the most part, modules are made to be independant of each others, but it can
be useful to have interplay. The dataset provides some basic API that modules
can leverage like :meth:`.Dataset.get_source` or :meth:`.Dataset.get_data`. For
more specific features the package contains some abstract base classes that
define the methods to be expected: for for instance
:class:`loader.LoaderAbstract` and :class:`writer.WriterAbstract`. See
:doc:`existing_modules` for a list of available plugins. See
:class:`.SplitWriterMixin` for an example of interplay facilitator and the
implementation of :class:`.XarraySplitWriter` that has multiple submodules
parents as discussed in the paragraph above.


Dataset parameters
==================

A dataset instance is supposed to represent a specific set of parameters.
Changing parameters might affect modules, and thus it is recommended to change
parameters using :meth:`.Dataset.set_params` or :meth:`.Dataset.reset_params`.
After the parameters have been modified, this function will launch all "reset
callbacks" that have been registered by modules. For instance, some modules may
use a cache and need to void it after a parameters change.

It might be useful to quickly change parameters, eventually multiple times,
before returning to the initial set of parameters. To this end, the method
:meth:`.Dataset.save_excursion` will return a context manager that will
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
default is a simple dictionary storing the parameters: :class:`.ParamsManager`.
The package also provides :class:`.ParamsManagerSection` where parameters are
stored in a :class:`data_assistant.config.section.Section` object. By specifying
the exact expected type of the parameters, this can ensure the existence of
parameters::

    class MyParameters(Section):
        threshold = Float(0.5)

    class Dataset(ParamsSectionPlugin, DataManagerBase):

        params: MyParameters

Now we are sure that ``Dataset().params`` will contain a ``threshold``
attribute. This comes at the cost of flexibility since sections are not as
malleable as other mutable mapping types.

.. note::

   The abstract parameters module is expecting that the parameters are stored
   in a :class:`~collections.abc.MutableMapping`. The Section class implements
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
modules'. It will instantiate and initialize all modules and store them in
:attr:`.ModuleMix.base_modules`.

This is used for instance to obtain the :class:`union<.SourceUnion>` or
:class:`intersection<.SourceIntersection>` of source files obtained by different
source modules.

Mixes class should be created with the class method :meth:`~.ModuleMix.create`.
For instance with::

    _Source = SourceUnion.create([SourceOne, SourceTwo])

we will obtain files catched by *SourceOne* and *SourceTwo* (without overlap)
when calling ``data_manager.get_source()``.

Mixes can run methods on its base modules, the name of the method to run can be
passed to several methods:

* ``apply_all`` will run on **all** the base modules of the mix and return a
  list of outputs.
* ``apply_select`` will only run on a **single** module. It will be selected
  by a user defined function that can be set in :meth:`~.ModuleMix.create` or
  with :meth:`.ModuleMix.set_select`. It chooses the appropriate base module
  based on the current state of the mix module, the dataset manager and its
  parameters, and eventual keywords arguments it might receive. It should return
  the class name of one of the module.

For instance, ``ds.source.apply_select("get_files")`` will return the files
obtained by the selected base module.

:meth:`~.ModuleMix.apply` will use the *all* or *select* version based on the
value of the *all* argument. In all methods, *args* and *kwargs* are passed to
the method that is run, and the *select* keyword argument is a passed to the
selection function.
