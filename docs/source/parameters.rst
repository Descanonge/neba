
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


Input parameters
================

From configuration files
++++++++++++++++++++++++

From the command line
+++++++++++++++++++++


Accessing parameters
====================

Convert to a dictionary. Nested or flat.

Accessing using attributes.

Get a list of parameters.

Get the parameters in a function signature.
