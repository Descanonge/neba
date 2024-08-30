
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

Subschemes can also be directly defined inside another scheme class definition.
The name of a nested class will be used a its corresponding subscheme instance,
and its definition will be moved under the attribute ``_{name}SchemeDef`` (its
name will also be changed to this). For example::

    class MyConfig(Scheme):

        class log(Scheme):
            level = Unicode("INFO")

        class sst(Scheme):
            dataset = Enum(["a", "b"])

            class a(Scheme):
                location = Unicode("/somewhere")
                time_resolution = Int(8, help="in days")

            class b(Scheme):
                location = Unicode("/somewhere/else")

This syntax may feel somewhat unorthodox, and the automatic promotion of
attributes can be disabled by directly setting the class attribute
:attr:`Scheme._dynamic_subschemes`. A plugin which allow mypy to keep up with
this is available. Add it to the list of plugins in your mypy configuration file
such as (for pyproject.toml)::

    [mypy]
    plugins = ['data_assistant.config.mypy_plugin']


The principal scheme, at the root of the configuration tree, is the
:class:`application<.application.ApplicationBase>`. It can hold directly all
your parameters, or nested sub-schemes. It will be responsible to gather the
parameters from configuration files and the command line.

Here is a rather simple example::

     from data_assistant.config import ApplicationBase, Scheme
     from traitlets import Bool, Float, Int, List, Unicode


     class App(ApplicationBase):

        class computation(Scheme):
            parallel = Bool(False, help="Conduct computation in parallel if true.")
            n_cores = Int(1, help="Number of cores to use for computation.")

        class physical(Scheme):
            threshold = Float(2.5, help="Threshold for some computation.")
            data_name = Unicode("SST")
            years = List(
                Int(),
                default_value=[2000, 2001, 2008],
                min_length=1,
                help="Years to do the computation on."
            )

     >>> app = App()
     >>> app.physical.years = [2023, 2024]

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
The methods :meth:`.Scheme.values_recursive`, :meth:`.Scheme.traits_recursive`,
and :meth:`.Scheme.defaults_recursive` return nested or flat dictionaries
of all the parameters the scheme (and its sub-schemes) contains. To limit to
only the parameters of this scheme (and *not* its sub-schemes) use
:meth:`.Scheme.values` with arguments ``(subschemes=False, recursive=False)``.

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

.. _mapping-interface:

Mapping interface
-----------------

The Scheme class also implements the interface of a
:external+python:ref:`mapping<collections-abstract-base-classes>` (notably for
instance :meth:`~.Scheme.keys`, :meth:`~.Scheme.values`, :meth:`~.Scheme.items`,
:meth:`~.Scheme.get`, as well as contains, iter, and len operations).
The keys to access this mapping can directly lead to a deeply nested parameter,
by joining the successive subschemes names with dots like so::

    >>> app["some.deeply.nested.parameter"]
    the parameter value

To modify the parameter values, one can access to it directly as we have seen,
but we can also use the set-item operation, both are equivalent::

    app.some.deeply.nested.parameter = 3
    app["some.deeply.nested.parameter"] = 3

Additionally, it implements an :meth:`~.Scheme.update` method allowing to modify
a scheme with a mapping of several parameters::

    app.update({"computation.n_cores": 10, "physical.threshold": 5.})

It can add new traits to the scheme with some specific input, see the docstring
for details. This should be considered experimental (even more so than the rest
of this library anyway).

Some other methods of :class:`dict`, such as binary-or, could be implemented in
the future.


Obtaining subsets of all parameters
-----------------------------------

Using :meth:`.Scheme.select` we can select only some of the parameters by name::

  >>> app.select("physical.threshold", "computation.n_cores", flatten=True)
  {
      "physical.threshold": 2.5,
      "computation.n_cores": 1
  }

.. note::

   Users wanting to automate some logic on nested dictionaries can lever the
   method :meth:`.Scheme.remap` that map a user function on a nested (or flat)
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
:meth:`.Scheme.trait_values_from_func_signature` will find the parameters that
share the same name as arguments in the function signature.

Input parameters
================

Procedure
---------

The :class:`.ApplicationBase` class allows to retrieve the values of parameters
from configuration files or from command line arguments (CLI), when
:meth:`.ApplicationBase.start` is launched. It first parses command line
arguments (unless deactivated) and then load values from specified configuration
files. Each time parameters are loaded from any kind of source, the parameters
for the application object are immediately applied to it, since they can alter
the rest of the process.

The parameters found are then normalized: each resulting parameter key is unique
and unambiguous. This provides a first layer of checking the input: keys that do
not lead to a known parameter will raise errors. This permit to merge the
parameters obtained from different files and CLI. Finally, the application will
recursively instanciate all schemes while passing the configuration values.
Unspecified values will take the trait default value. All values will undergo
validation from traitlets.

.. note::

   In some specific cases, instanciating the whole configuration tree could be
   costly. It is thus possible to deactivate the automatic instanciation with
   :attr:`.ApplicationBase.auto_instanciate` and arguments to
   :attr:`.ApplicationBase.start`. However, a parameters value can only be
   verified by a trait if its container is instanciated.

In all cases (files and CLI) the configuration values are retrieved by a
:class:`.ConfigLoader` subclass adapted for the source. Its output will be a
**flat** dictionary mapping *resolved keys* to :class:`.ConfigValue`.

A "resolved" key is a succession of attribute names pointing to a trait,
starting from the application. It is thus unique. With the same example as above
for instance: ``physical.years``. There can be more levels if the configuration
is deeply nested ``scheme.subscheme.sub_subscheme.etc.traitname``.

.. important::

    It is possible to define aliases with the :attr:`.Scheme.aliases` attribute.
    It is a mapping of shortcut names to a deeper subscheme::

        {"short": "some.deeply.nested.subscheme"}

    Aliases are expanded when the configuration is resolved.

A parameter can also be input as a "class-key", similarly to how it is done in
vanilla traitlets. It consists of the name of scheme class and a trait name:
``SomeSchemeClassName.trait_name``. It cannot be nested further (this
complicates how to do merging quite a bit). When the configuration is resolved,
class-keys are transformed to the corresponding fully resolved key(s). Still
with the same example: ``PhysicalParams.years`` will be resolved to
``physical.years``.

The value associated to a class-key, even after being resolved, is given a
lower priority. So if we somehow input::

    physical.threshold = 1
    PhysicalParams.threshold = 5

After merging configurations, the retained value will be 1, whatever the order
the keys were given in.

.. note::

   Unlike vanilla traitlets, the way we populate instances allows to have
   multiple instances of the same Scheme with different configurations. This
   is why a single class-key can point to multiple locations in the
   configuration tree.


From configuration files
------------------------

The application can take parameter values from configuration files by invoking
:meth:`.ApplicationBase.load_config_files`. It will load the file (or files)
specified in :attr:`.ApplicationBase.config_files`. If multiple files are
specified, the parameter from one file will replace those from the previous
files in the list. The resulting configuration will be stored in the
:attr:`~.ApplicationBase.file_conf` attribute. Different file formats require
specific subclasses of :class:`~.FileLoader`. For each file, the first
FileLoader subclass in :attr:`.ApplicationBase.file_loaders` to be adequate will
be used.

.. note::

   The class method :meth:`.FileLoader.can_load` returns whether it is capable
   of handling a file. Currently, it only looks at the file extension, but more
   advanced logic could be implemented if necessary.

As any other subclass of :class:`.ConfigLoader`, :class:`.FileLoader` needs only
to implement the :meth:`~.ConfigLoader.load_config` method that needs to
populate the flat configuration dictionary at :attr:`~.ConfigLoader.config`.
ConfigLoader will ensure that the configuration is resolved, cleaned-up and
ready to be used by the application.

.. note::

   A "flat configuration dictionary" is a simple dictionary mapping keys
   leading to traits in the configuration tree to :class:`.ConfigValue`
   instances. The keys can contains aliases or be class-keys that will be
   automatically resolved later.

   The :class:`.ConfigValue` class allows to store more information about the
   value: its provenance, the original string and parsed value if applicable,
   and a priority value used when merging configs. To obtain a value, simply use
   :meth:`.ConfigValue.get_value`.

The file loaders have an additional feature in the :meth:`.FileLoader.to_lines`
method. It generates the lines for a valid configuration file of the
corresponding format, following the default values of the application
subschemes. If the file loader has its :attr:`~.ConfigLoader.config` dictionary
populated (manually or by reading from an existing file) it will use these
values instead. This allows to generate lengthy configuration files, with
different amounts of additional information in comments. The end user can simply
use :meth:`.ApplicationBase.write_config` which automatically deals with an
existing configuration file that may need to be updated, while keeping its
current values (or not).

.. note::

    To avoid importing too much automatically, especially since some loaders
    rely on third-party libraries that may be missing, and to avoid having to
    resort to some kind of lazy-loading (slightly more cumbersome to write),
    file loaders are placed in their own sub-module. So to allow TOML and Python
    configuration files, we would need to do::

        from data_assistant.config.loaders.python import PyFileLoader
        from data_assistant.config.loaders.toml import TomlkitLoader

        class Application(ApplicationBase):
            file_loaders = [PyFileLoader, TomlkitLoader]

            ...

The package supports and recommends `TOML <https://toml.io>`__ configuration
files. It is both easily readable and unambiguous. Despite allowing nested
configuration, it can be written without indentation, allowing to add long
comments for each parameters. The :external+python:mod:`tomllib` builtin module
does not support writing, so we use (for both reading and writing) one of the
recommended replacement: `tomlkit <https://pypi.org/project/tomlkit>`__ in
:class:`.TomlkitLoader`.

The package also support python scripts as configuration files, similarly to how
traitlets is doing it. To load a configuration file, the file loader
:class:`.PyLoader` creates a :class:`.PyConfigContainer` object. That object
will be bound to the ``c`` variable in the script/configuration file. It allows
arbitrarily nested attribute setting so that the following syntax is valid::

    c.group.subgroup.parameter = 5
    c.ClassName.parameter = True

.. important::

    Remember that this script will be **executed**, so arbitrary code can be run
    inside, maybe changing some value depending on the OS, the hostname, or more
    advanced logic.

    Of course running arbitrary code dynamically is a security liability, do not
    load parameters from a python script unless you trust it.

The loader do not support the traitlets feature of configuration file
inheritance via (in the config file) ``load_subconfig("some_other_script.py")``.
This would be doable, but for the moment we recommend instead that you specify
multiple configuration files in :attr:`.ApplicationBase.config_files`,
remembering that each configuration file replaces the values of the previous one
in the list.

Despite not being easily readable, the JSON format is supported via
:class:`.JsonLoader` and the builtin module :external+python:mod:`json`. The
decoder and encoder class can be customized.

It is planned to add support for Yaml format via :class:`.YamlLoader` and a
third party module to be chosen.

From the command line
---------------------

Parameters can be set from parsing command line arguments, although it can be
skipped by either setting the :attr:`.ApplicationBase.ignore_cli` trait or
the `ignore_cli` argument to :meth:`.ApplicationBase.start`. The configuration
obtained will be stored in the :attr:`~.ApplicationBase.cli_conf` attribute and
will take priority over parameters from configuration files.

The keys are indicated following one or two hyphen. Any subsequent hyphen is
replaced by an underscore. So ``-computation.n_cores`` and
``--computation.n-cores`` are equivalent. As already node, parameters keys can
be dot-separated paths leading to a trait. Aliases can be used for brevity.
Class-keys are input with the same syntax (``--ClassName.trait_name``).

.. note ::

    The list of command line arguments is obtained by
    :meth:`.ApplicationBase.get_argv`. By default, it returns None, so that it
    is left to the underlying parser to do it. But more logic could be input
    there, for instance to deal with multiple layers of arguments separated by
    double hyphens.

The loading of command line parameters is done by :class:`.CLILoader`. One of
the main differences with other loaders is that all arguments need to be parsed.
This is done by :meth:`.ConfigValue.parse` that, at the time of parsing, should
have a reference to the corresponding trait (which itself has methods
``from_string`` and ``from_string_list`` for containers).

Extra parameters to the argument parser can be added using
:meth:`.ApplicationBase.add_extra_parameter`. The values will be available after
CLI parsing in :attr:`.ApplicationBase.extra_parameters`.

.. note:: Implementation details

    :class:`.CLILoader` relies on the builtin :external+python:mod:`argparse`.
    Rather than listing all possible keys to every parameters (accounting for
    aliases and class-keys) as would normally be required, we borrow some
    trickery from traitlets. The dictionaries holding the actions
    (``argparse.ArgumentParser._option_string_actions`` and
    ``argparse.ArgumentParser._optionals._option_string_actions``) are replaced
    by a dict subclass :class:`.DefaultOptionDict` that creates a new action if
    a key is missing (ie whenever a parameter is given).

So for any and every parameter, the argument :external+python:ref:`action` is
"append", with type :class:`str` (since the parsing is left to traitlets), and
``nargs="*"`` meaning that any parameter can receive any number of values.
To indicate multiple values, for a list trait for instance, the following syntax
is to be used::

    --physical.years 2015 2016 2017

**and not** as is the case with vanilla traitlets::

    --physical.years 2015 --physical.years 2016 ...

This will raise an error, to avoid possible errors in user input due to
inattention.

.. note::

   The default action can be changed, check the documentation and code of
   :mod:`.config.loader` for more details.


From a dictionary
-----------------

The loader :class:`.DictLikeLoader` can transform any nested mapping into a
proper configuration object (flat dictionary mapping do-separated keys to
:class:`.ConfigValue`). It deals in a quite straightforward manner with the
issue of differentiating between a nested mapping corresponding to an eventual
trait and one corresponding to further nesting in a subscheme. It simply checks
if the key is a known subscheme or alias, otherwise it assumes the key
corresponds to a parameter value.

.. note::

    The file loaders :class:`.YamlLoader` and :class:`.JsonLoader` are based on
    it, as they only return a nested mapping without means to differentiate the
    two types of nesting.
