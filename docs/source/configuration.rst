
.. currentmodule:: data_assistant

************************
Configuration management
************************

This package provide a submodule :mod:`.config` to help managing the parameters
of a project. It requires to specify the parameters in python code: their type,
default value, help string, etc. It relies on the
`traitlets <https://traitlets.readthedocs.io>`__ package to do this, in which we
can define *traits*: class attributes that are type-checked. More on the
motivations behind the design choices :doc:`here<motivations>`.

.. note::

   The main difference with the "vanilla" traitlets package is that we allow
   nested configurations. We replace :class:`traitlets.config.Configurable` by
   our subclass :class:`~config.scheme.Scheme` and use our own
   :class:`~config.application.ApplicationBase` class.

Once defined, the parameters values can be recovered from configuration files
(python files like with traitlets, but also TOML or YAML files), and
from the command line as well.

The help string of each trait is used to generate command line help,
fully documented configuration files, and a the plugin :mod:`.autodoc_trait`
integrates it in sphinx documentations.

.. currentmodule:: data_assistant.config

Specifying parameters
=====================

Parameters are specified as class attributes of a :class:`~.scheme.Scheme`
class, and are subclasses of :class:`traitlets.TraitType` (for instance
:class:`~traitlets.Float`, :class:`~traitlets.Unicode`, or
:class:`~traitlets.List`).

.. _traits-explain:

.. note::

   Traits can be confusing at first. They are a sort of
   :external+python:doc:`descriptor<howto/descriptor>`. A trait is an
   **instance** bound to a **class**. Let's take for instance::

     class Container(Scheme):
         name = Float(default_value=1.)

   From this we can access the trait instance with ``Container.name``, but it
   only contain the parameters used for its definition, **it does not hold any
   actual value**.

   But if we create an **instance of the container**, when we access ``name``
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
configuration. It can be done by using the :func:`~scheme.subscheme` function
and setting it as an attribute in the parent scheme::

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

   which automatically call ``subscheme()`` under the hood. This is shorter but
   can be confusing, in particular for static type checkers.

The principal scheme, at the root of the configuration tree, is the
:class:`application<.application.ApplicationBase>`. It can hold directly all
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
accessed (or changed) like attributes of the scheme instance that contains them.
This has the advantages to allow for deeply nested access::

  app.some.deeply.nested.trait = 2

It also is still using the features of traitlets: type checking, value
validation, "on-change" callbacks, dynamic default value generation. This can
ensure for instance that a configuration stays valid.
Refer to the :external+traitlets:doc:`traitlets documentation<using_traitlets>`
for more details on how to use these features.

Obtaining all parameters
------------------------

But of course, it is often necessary to pass parameters to code that is not
supporting Schemes.
Thus Schemes allow to obtain parameters in more universal python dictionaries.
The methods :meth:`Scheme.values_recursive`, :meth:`Scheme.traits_recursive`,
and :meth:`Scheme.defaults_recursive` return nested or flat dictionaries
of all the parameters the scheme (and its sub-schemes) contains. To limit to
only the parameters of this scheme (and *not* its sub-schemes) use
:meth:`Scheme.values` with arguments ``(subschemes=False, recursive=False)``.

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

Mapping interface
-----------------

The Scheme class also implements the interface of a
:external+python:ref:`mapping<collections-abstract-base-classes>` (notably for
instance :meth:`~Scheme.keys`, :meth:`~Scheme.values`, :meth:`~Scheme.items`,
:meth:`~Scheme.get`, as well as contains, iter, and len operations).
The keys to access this mapping can directly lead to a deeply nested parameter,
by joining the successive subschemes names with dots like so::

    >>> app["some.deeply.nested.parameter"]
    the parameter value

To modify the parameter values, one can access to it directly as we have seen,
but we can also use the set-item operation, both are equivalent::

    app.some.deeply.nested.parameter = 3
    app["some.deeply.nested.parameter"] = 3

Additionally, it implements an :meth:`~Scheme.update` method allowing to modify
a scheme with a mapping of several parameters::

    app.update({"computation.n_cores": 10, "physical.threshold": 5.})

It can add new traits to the scheme with some specific input, see the docstring
for details. This should be considered experimental (even more so than the rest
of this library anyway).

Some other methods of :class:`dict`, such as binary-or, could be implemented in
the future.


Obtaining subsets of all parameters
-----------------------------------

Using :meth:`Scheme.select` we can select only some of the parameters by name::

  >>> app.select("physical.threshold", "computation.n_cores", flatten=True)
  {
      "physical.threshold": 2.5,
      "computation.n_cores": 1
  }

.. note::

   Users wanting to automate some logic on nested dictionaries can lever the
   method :meth:`Scheme.remap` that map a user function on a nested (or flat)
   dictionary of traits.

   Functions :func:`.util.nest_dict` and :func:`.util.flatten_dict` can also
   be useful in manipulating dictionaries.

Some parameters may be destined for a specific function. It is possible to
select those by name as shown above, or one could tag the target traits during
definition like so::

  some_parameter = Bool(True).tag(for_this_function=True)

These traits can then automatically be retrieved using the `metadata` argument
of the function above (adding ``for_this_function=True`` to the call).
Schemes also feature a specialized function for this use case:
:meth:`Scheme.trait_values_from_func_signature` will find the parameters that
share the same name as arguments in the function signature.

Input parameters
================

The :class:`~.application.ApplicationBase` class allows to retrieve the values
of parameters from configuration files or from command line arguments (CLI),
when :meth:`.ApplicationBase.start` is launched.

It first parses command line arguments (unless deactivated). It then load
values from specified configuration files. Each time parameters are loaded from
any kind of source, the parameters for the application are immediately applied
to it, since they kind alter the rest of the process. The parameters found
are then normalized: each resulting parameter key is unique and unambiguous.
This provides a first layer of checking the input: keys that do not lead to
a known parameter will raise errors.
This permit to merge the parameters obtained from different files and CLI.
Finally, the application will recursively instanciate all schemes while passing
the configuration values. Unspecified values will take the trait default value.
All values will undergo validation from traitlets.

.. note::

   Instanciating the whole configuration tree could be costly in particular
   use cases, and can be bypassed.

   However, a new value can only be fully verified by a trait when its
   container is instanciated. Thus it is recommended.

In all cases (files and CLI) the configuration values are retrieved by a
:class:`~.loader.ConfigLoader` subclass adapted for the source. Its output
will be a **flat** dictionary mapping *keys* to :class:`~.loader.ConfigValue`.

A "resolved" key is a succession of attribute names pointing to a trait,
starting from the application. It is thus unique. With the same example as above
for instance: ``physical.years``. There can be more levels if the configuration
is deeply nested ``scheme.subscheme.sub_subscheme.etc.traitname``.

.. important::

    It is possible to define aliases with the :attr:`.Scheme.aliases` attribute.
    It is a mapping of shortcut names to a deeper subscheme::

        {"short": "some.deeply.nested.subscheme"}

    Aliases are expanded when the configuration is resolved.

A parameter can also be input as a "class-key", as it was done in vanilla
traitlets. It consist of the name of scheme class and a trait name:
``SomeSchemeClassName.trait_name``. It cannot be nested further (this
complicates how to do merging quite a bit). When the configuration is resolved,
class-keys are transformed to the corresponding fully resolved key(s).
Still with the same example: ``PhysicalParams.years`` will be resolved to
``physical.years``.

The value associated to a class-key, even after being resolved, is given a
lower priority. So if given::

    physical.threshold = 1
    PhysicalParams.threshold = 5

After merging configurations, the retained value will be 1, whatever the order
the keys were given in.

.. note::

   Unlike *vanilla* traitlets, the way we populate instances allows to have
   multiple instances of the same Scheme with different configurations. This
   is why a single class-key can point to multiple locations in the
   configuration tree.


From configuration files
------------------------

From configuration files.
Basically we recover a nested dictionary from typical config file formats like
YAML and TOML.

TOML: we use tomlkit. A different library could be used as a backend.
yaml: its in standard python.

Python: like traitlets, we run a python file.
describe syntax.
At the moment, no sub-config.

From the command line
---------------------

The traits are indicated following one or two hyphen. Any subsequent hyphen is
replaced by an underscore. So ``-computation.n_corse`` and
``--computation.n-cores`` are equivalent.

The parsing is done by the trait object using
:meth:`traitlets.TraitType.from_string`. Each parameter can receive one or more
values that will always be interpreted as a list. Actually more complicated from_string_list.

Implementation detail: it is difficult to account for every way a trait can be
indicated. Instead any parameter is accepted by argparser (there is a little
trickery explained in the module :mod:`.config.loader`).
