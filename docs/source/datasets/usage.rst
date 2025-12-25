

*****
Usage
*****

.. _module-system:

Module system
=============

This framework tries to make those data managers objects as universal as
reasonably possible. The base class does not specify a data source (it could be
one file, multiple files, a remote datastore, ...) or a data type (it could be
opened by different libraries).

Definition in the data manager
------------------------------

The default :class:`.Dataset` has four modules. Each module has an attribute
where the module instance can be accessed, and an attribute where its type can
changed:

+---------------+------------+----------------------------------+-------------+
| Instance      | Definition | Class                            |  Function   |
| attribute     | attribute  |                                  |             |
+===============+============+==================================+=============+
| params_manager| Params     | :class:`.ParamsManagerAbstract`  | manage      |
|               |            |                                  | parameters  |
+---------------+------------+----------------------------------+-------------+
| source        | Source     | :class:`.SourceAbstract`         | manage      |
|               |            |                                  | data source |
+---------------+------------+----------------------------------+-------------+
| loader        | Loader     | :class:`.LoaderAbstract`         |  load data  |
+---------------+------------+----------------------------------+-------------+
| writer        | Writer     | :class:`.WriterAbstract`         | write data  |
+---------------+------------+----------------------------------+-------------+


To change a module, we only need to change the module type contained in the
corresponding attribute. It is expected to be done in a Dataset subclass. It can
be a simple attribute change, or a class definition with the appropriate name,
like so::

    # simple attribute changes
    class DataManagerProjet(Dataset):
        """Define a data-manager base for the project."""

        Source = SimpleSource
        Loader = XarrayLoader

    # more complex definitions
    class SST(DataManagerProject):

        class Source(DataManagerProject.Source):

            def get_source(self):
                ...

        class Loader(DataManagerProject.Loader):
            def postprocess_data(self, data):
                ...

Defining new modules
--------------------

Users will typically only need to use existing modules, possibly with
redefining some of its methods. In the case more dramatic changes are necessary,
here are more details on the module system.

The correspondence between the attribute containing the module instance and the
one containing the module type must be indicated in
:attr:`~.Dataset._modules_attributes`.

.. note::

   The module will be instanciated in the order of the mapping. They will also
   be setup in this order, with the difference that the parameters module will
   always be first.

Dataset managers are initialized with an optional argument giving the
parameters, and additional keyword arguments. All modules are instantiated with
the same arguments. Immediately after, their :attr:`~.Module.dm` attribute is
set to the containing data manager. Once they are all instantiated, they are
setup using the :meth:`.Module.setup` method. This allow to be (mostly) sure
that all other module exist if there is need for interplay.

.. note::

   'Mostly' because if a module fails to instantiate and its attribute
   :attr:`.Module._allow_instantiation_failure` is True, there will only log a
   warning and the module will not be accessible.

The :meth:`~.Module.setup()` method is planned for inheritance cooperation. Each
new subclass should make a ``super().setup()`` call whenever appropriate. The
parent function launched by the Dataset (:meth:`.Module.__setup`) will make sure
it will be called for every base class. So for instance in ``class
NewModule(SubModuleA, SubModuleB)`` both ``SubModuleA.setup`` and
``SubModuleB.setup`` will be called, even though they don't necessarily know
about each other.

.. important::

   It is still necessary to add a ``super().setup()`` to propagate the call
   further; for instance, if SubModuleB is a child of SubModuleC and we want
   ``SubModuleC.setup`` to run.

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
default is a simple dictionary storing the parameters. Any
:class:`~collections.abc.MutableMapping` can be used. To be sure that a
function or module be compatible, prefer accessing parameters as a mapping.

The package also provides :class:`.ParamsManagerSection` where parameters are
stored in a :class:`data_assistant.config.section.Section` object. By specifying
the exact expected type of the parameters, this can ensure the existence
of parameters::

    class MyParameters(Section):
        threshold = Float(0.5)

    class Dataset(ParamsSectionPlugin, DataManagerBase):

        params: MyParameters

Now we are sure that ``Dataset().params`` will contain a ``threshold``
attribute. This comes at the cost of flexibility since sections are not as
malleable as other mutable mapping types.

Changing parameters might affect modules. In particular, modules using a cache
will need to be reset when parameters are changed. They can be changed with
:meth:`.Dataset.set_params` or :meth:`.Dataset.reset_params` which will trigger
all "reset callbacks" that have been registered by modules.
For :class:`section<.ParamsManagerSection>` and :class:`dict<ParamsManagerDict>`
modules, the parameters can be changed directly and a callback will reset
the dataset correctly.

.. important::

   This does not include in-place operations on mutable parameters::

     dm.params["my_list"].append(1)

   will ***not** trigger a callback.

.. important::

   Dictionaries are actually a special subclass with a patched ``__set__``
   method. The dictionary is considered to be **flat**. Nested dicts are not
   transformed into this special class::

     dm.params["my_sub_params"]["key"] = 1

   will **not** trigger a callback.



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
