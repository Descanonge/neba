
.. currentmodule:: data_assistant

Parameters management
---------------------

This package provide a submodule :mod:`.config` to help managing the parameters
of a project.
It requires to specify the parameters in python code: their type, default value,
help string, etc. It relies on the :mod:`traitlets` package to do this, in which
we can define *traits*: class attributes that are type-checked.

.. note::

   This package extends functionality by allowing nested configurations. We
   replace :class:`traitlets.config.Configurable` by our subclass
   :class:`~config.scheme.Scheme` and use our own
   :class:`~config.application.ApplicationBase` class.

Once defined, the parameters values can be recovered from configuration files
(python files like with traitlets, but also TOML or YAML files), and
from the command line.

The help string of each trait is used to generate command line help,
fully documented configuration files, and a the plugin :mod:`.autodoc_trait`
integrates it in sphinx documentations.

.. currentmodule:: data_assistant.config

Specifying parameters
=====================

Parameters are specified as class attributes of a :class:`~.scheme.Scheme`
class, and are of type :class:`traitlets.TraitType` (for instance
:class:`~traitlets.Float`, :class:`~traitlets.Unicode`, or
:class:`~traitlets.List`).

.. _traits-explain:

.. note::

   Traits can be confusing at first. They are a sort of
   :external+python:doc:`descriptor<howto/descriptor>`. They are used as
   **instances** bound to a **class**. For instance::

     class Container(Scheme):
         name = Float(default_value=1.)

   From this we can access the trait instance with ``Container.name``, but this
   instance only contain the parameters used for its definition, **it does not
   hold any actual value**.

   But if we create an *instance* of the container, when we access ``name``
   we will obtain a value, **not a trait**::

     >>> c = Container()
     >>> type(c.name)
     float
     >>> c.name = 2  # we can change it
     >>> c.name
     2.0

   It behaves nearly like a typical float attribute. When we change the value
   for instance, the trait (again which is a *class attribute*) will be used
   to validate the new value, or do some more advanced things. But the value
   is tied to the container instance ``c``.

A scheme can contain other sub-schemes, allowing a tree-like, nested
configuration. It can be done by simply using the :func:`~scheme.subscheme`
function and setting it as an attribute in the parent scheme::

    from data_assistant.config import subscheme

    class ChildScheme(Scheme):
        param_b = Int(1)

    class ParentScheme(Scheme):
        param_a = Int(1)

        child = subscheme(ChildScheme)

In the example above we have two parameters available at ``param_a`` and
``child.param_b``.

.. note::

   It is also possible to directly write::

     child = ChildScheme

   which automatically transform the attribute in a :class:`traitlets.Instance`.
   This is shorter but can be confusing, in particular for static type checkers.

The principal scheme, at the root of the configuration tree, is the
:class:`Application<.application.ApplicationBase>`. It can hold directly all
your parameters, or nested sub-schemes. It will be responsible to gather the
parameters from configuration files and the command line.

Here is a rather simple example::

     from data_assistant.config import ApplicationBase, Scheme, subscheme
     from traitlets import Bool, Float, Int, List, Unicode

     class ComputationParams(Scheme):
         parallel = Bool(False, help="Conduct computation in parallel if true.")
         n_cores = Int(1, help="Number of cores to use for computation.")

     class PhysicalParams(Scheme):
         threshold = Float(2.5, help="Threshold for some computation.")
         data_name = Unicode("SST")
         years = List(
             Int(),
             default_value=[2000, 2001, 2008],
             min_length=1,
             help="Years to do the computation on."
          )

     class App(ApplicationBase):
         computation = subscheme(ComputationParams)
         physical = subscheme(PhysicalParams)

     >>> app = App()
     >>> app.physical.years = [2023, 2024]

.. currentmodule:: data_assistant.config.scheme

Accessing parameters
====================

As explained :ref:`above<traits-explain>`, the **value** of parameters can be
accessed (or changed) as attributes of the scheme instance that contains them.
This has the advantages to allow for deeply nested access::

  app.some.deeply.nested.trait = 2

It also is still using the features of traitlets: type checking, value
validation, "on-change" callbacks, dynamic default value generation. This can
ensure for instance that a configuration stays valid.

But of course, it is often necessary to pass parameters to code that is not
supporting Schemes.
Thus Schemes allow to obtain parameters in more universal python dictionaries.
The methods :meth:`Scheme.values_recursive`, :meth:`Scheme.traits_recursive`,
and :meth:`Scheme.defaults_recursive` return a nested or flat dictionary
of all the parameters the scheme (and its sub-schemes) contains. To limit to
only the parameters of this scheme (and *not* its sub-schemes) use
:meth:`Scheme.values`.

So for instance we can retrieve all our application parameters::

  >>> app.values_recursive()
  {
      ... application related parameters like
      log_level: "INFO",
      ...
      "computation": {
          "parallel": False,
          "n_cores": 1
      },
      "physical": {
          "threshold": 2.5,
          "data_name": "SST",
          "years": [2023, 2024]
      }
  }

It works for any scheme instance, so we can retrieve only the computation
parameters::

  >>> app.computation.values_recursive()
  {
      "parallel": False,
      "n_cores": 1
  }

Using :meth:`Scheme.values` we can select only some of the parameters by name::

  >>> app.physical.values(select=["threshold", "data_name"])
  {
      "threshold": 2.5,
      "data_name": "SST"
  }

.. note::

   Users wanting to automate some logic on nested dictionaries can lever the
   method :meth:`Scheme.remap` that map a user function on a nested (or flat)
   dictionary of traits.

Some parameters may be destined for a specific function. It is possible to
select those by name as shown above, or one could tag the target traits during
definition like so::

  some_parameter = Bool(True).tag(for_this_function=True)

These traits can then automatically be retrieved using the `metadata` argument
of the function above.
Schemes also feature a specialized function for this use case:
:meth:`Scheme.trait_values_from_func_signature` will find the parameters that
share the same name as argument in the function signature.


Input parameters
================

Goal: fill the Schemes.

The application recovers configuration values from different sources, combines
them, and when instanciating update the values of each Scheme instance.

.. note::

   Instanciating the whole configuration tree could be costly in particular
   use cases, and can be bypassed.

   However, a new value can only be fully verified by a trait when its
   container is instanciated. Thus it is recommended.

A configuration is a **flat** dictionary whose keys indicate to which trait(s)
this key correspond to.

.. important::

   Unlike *vanilla* traitlets, the way we populate Schemes allows to have
   multiple instances of the same configurable (ie scheme) with different
   configurations.

The key can be a succession of attribute names pointing to a trait, start from
the application. With the same example as above for instance:
``physical.years``. There can be more levels if the configuration is deeply
nested ``scheme.subscheme.sub_subscheme.etc.traitname``.

Some levels can be aliases.
More on aliases ? Not really implemented.

Can be "Class keys": ``SomeSchemeClassName.trait_name``.

From configuration files
++++++++++++++++++++++++

From configuration files.
Basically we recover a nested dictionary from typical config file formats like
YAML and TOML.

TOML: we use tomlkit. A different library could be used as a backend.
yaml: its in standard python.

Python: like traitlets, we run a python file.
describe syntax.
At the moment, no sub-config.

From the command line
+++++++++++++++++++++

The traits are indicated following one or two hyphen. Any subsequent hyphen is
replaced by an underscore. So ``-computation.n_corse`` and
``--computation.n-cores`` are equivalent.

The parsing is done by the trait object using
:meth:`traitlets.TraitType.from_string`. Each parameter can receive one or more
values that will always be interpreted as a list.

Implementation detail: it is difficult to account for every way a trait can be
indicated. Instead any parameter is accepted by argparser (there is a little
trickery explained in the module :mod:`.loader`).

Normalization of configuration keys
+++++++++++++++++++++++++++++++++++

This is all for merging configs together.
Question of order? We normalize config before merging them. Is there a specific
reason? It seems logical idk. It can technically be changed. TODO: Make it
easier tho.

A full-path key will have priority over other keys.

Remove aliases, replace by full path.

If a scheme class is contained in the configuration tree, ie the is a succession
of attributes lead from the Application to a trait: the value corresponding to
the key is duplicated for every scheme.

If a scheme class is **detached** from the configuration tree, the key it is
kept as is. (No full-path key can attain it).
