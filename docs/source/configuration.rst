
.. currentmodule:: data_assistant

************************
Configuration management
************************

This package provides a submodule :mod:`.config` to help managing the parameters
of a project. It requires to specify the parameters in python code: their type,
default value, help string, etc. It relies on the `traitlets
<https://traitlets.readthedocs.io>`__ package to do this

.. note::

   The main difference with the "vanilla" traitlets package is that we allow
   nested configurations. We replace :class:`traitlets.config.Configurable` by
   our subclass :class:`~config.section.Section` and use our own
   :class:`~config.application.ApplicationBase` class.

Once defined, the parameters values can be recovered from configuration files
(python files as for traitlets, but also TOML or YAML files), and
from the command line as well.

The help string of each trait is used to generate command line help (completion
on the way), fully documented configuration files, and the :mod:`.autodoc_trait`
plugin integrates it in sphinx documentations.

.. currentmodule:: data_assistant.config

Specifying parameters
=====================

The configuration is specified through :class:`~.section.Section` classes. Each
section contains parameters in the form of class attribute of type
:class:`traitlets.TraitType` (for instance :class:`~traitlets.Float`,
:class:`~traitlets.Unicode`, or :class:`~traitlets.List`), or other (nested)
sections.

.. _traits-explain:

.. note::

   Traits can be confusing at first. They are a sort of
   :external+python:doc:`descriptor<howto/descriptor>`. A container class
   has instances of traits bound as class attribute. For instance::

     class Container(Section):
         name = Float(default_value=1.)

   From this we can access the trait instance with ``Container.name``, but it
   only contains the information used for its definition, **it does not hold any
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

A section can contain other sub-sections, allowing a tree-like, nested
configuration. It can be done by using the :class:`~section.Subsection` class
and setting it as an attribute in the parent section::

    from data_assistant.config import subsection

    class ChildSection(Section):
        param_b = Int(1)

    class ParentSection(Section):
        param_a = Int(1)

        child = Subsection(ChildSection)

In the example above we have two parameters available at ``param_a`` and
``child.param_b``.

.. important::

   Like traits, Subsections are also descriptors: accessing
   ``ParentSection().child`` returns a ``ChildSection`` instance.

   To be more precise, Subsection creates a dummy subclass so that the same
   child section class can be used in multiple places in your configuration
   without clashes.

For ease of use and readability, subsections can also be defined directly inside
another section class definition. The name of such a nested class will be used
for the corresponding subsection attribute. The class definition will be renamed
and moved moved under the attribute ``_{name}SectionDef``. For example::

    class MyConfig(Section):

        class log(Section):
            level = Unicode("INFO")

        class sst(Section):
            dataset = Enum(["a", "b"])

            class a(Section):
                location = Unicode("/somewhere")
                time_resolution = Int(8, help="in days")

            class b(Section):
                location = Unicode("/somewhere/else")

    MyConfig().sst.a.location = "/fantastic"

As it could be seen as a bit unorthodox, the automatic promotion of sections can
be disabled by directly setting the class attribute
:attr:`Section._dynamic_subsections` to False.

A mypy plugin is provided to support these dynamic definitions. Add it to the
list of plugins in your mypy configuration file, for instance in
'*pyproject.toml*'::

    [mypy]
    plugins = ['data_assistant.config.mypy_plugin']


Application
===========

The principal section, at the root of the configuration tree, is the
:class:`Application<.application.ApplicationBase>`. As a subclass of
:class:`~.Section`, it can hold directly all your parameters, or nested
subsections. It will also be responsible for gathering the parameters from
configuration files and the command line, and more.

Here is a rather simple example::

     from data_assistant.config import ApplicationBase, Section
     from traitlets import Bool, Float, Int, List, Unicode


     class App(ApplicationBase):

        class computation(Section):
            parallel = Bool(False, help="Conduct computation in parallel if true.")
            n_cores = Int(1, help="Number of cores to use for computation.")

        class physical(Section):
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

Shared instance
---------------

The application class can provide a shared, global instance. It can be
accessed with :meth:`App.shared()<.ApplicationBase.shared>`, which will return
the shared instance, or create it and register it if it does not exist yet.
The standard ``App()`` will not register a shared instance.

Starting the application
------------------------

By default, when the application is instantiated it executes its starting
sequence with the :meth:`~.ApplicationBase.start` method. It will:

- Parse command line arguments
- Read parameters from configuration files
- Instantiate all subsections with the obtained parameters

This can be controlled with ``__init__`` arguments ``start``, ``ignore_cli``,
and ``instantiate``.

.. note::

    Even though some features are still available if the subsections are not
    instantiated (since the subsections classes contain information about
    the parameters), instantiating them is necessary to fully validate the
    parameters.

.. _orphans:

Orphan sections
---------------

By default, when starting the application, the section objects are instantiated.
However it might be desirable to have complex section objects that should not be
instantiated directly, or not at every execution.

To that end, the application provide the class decorator
:meth:`~.ApplicationBase.register_orphan()`. It will do two things:

- Register the section in the application. It will not be instantiated but its
  parameters will be known and retrieved.
- Register the application class in the section. It will then be used
  automatically to recover parameters from the shared instance when
  instantiating the section (if it exists). This can be deactivated by passing
  ``auto_retrieve=False`` to the register decorator.

For example::

    @App.register_orphan()
    class MyOrphan(Section):
        year = Int(2000)

    m = MyOrphan()

This will automatically start a global application instance, recover parameters
and apply it to the orphan section.

Logging
-------

The base application contains some parameters to easily log information. A
logger instance is available at :attr:`~.ApplicationBase.log` that will log to
the console (stderr), and can be configured via the (trait) parameters
:attr:`~.ApplicationBase.log_level`, :attr:`~.ApplicationBase.log_format`, and
:attr:`~.ApplicationBase.log_datefmt`.

The configuration of the logging setup is kept minimal. Users needing to
configure it further may look into :meth:`.ApplicationBase._get_logging_config`.

.. note::

   The logger will have the application class fullname (module + class name), so
   logging inheritance rules will apply.

Accessing parameters
====================

As explained :ref:`above<traits-explain>`, the **value** of parameters can be
accessed (or changed) like attributes of the section that contains them.
This has the advantages to allow for deeply nested access::

  app.some.deeply.nested.trait = 2

.. note::

    It also benefits from the features of traitlets: type checking, value
    validation, "on-change" callbacks, dynamic default value generation. This
    can ensure that a configuration stays valid. Refer to the
    :external+traitlets:doc:`traitlets documentation<using_traitlets>` for more
    details on how to use these features.

Sections also implements the interface of a
:class:`~collections.abc.MutableMapping` and most of the interface of a
:class:`dict`. Parameters can be accessed with a single key of dot-separated
attributes::

  app["some.deeply.nested.trait"] = 2
  # or
  app["some"]["deeply.nested.trait"] = 2

By default :meth:`~.Section.keys`, :meth:`~.Section.values` and
:meth:`~.Section.items` do not list subsections objects or aliases, but this
can be altered. They also return flat output; to obtain a nested dictionnary
pass ``nest=True``.

.. important::

    The omission of subsections and aliases is done to allow a straightforward
    conversion with ``dict(section)``. Similarly, ``len`` and ``iter`` do not
    account for subsections and aliases.

    However, other methods such as "get", "set" and "contains" will allow
    subsections keys and aliases::

        >>> "subsection" in section
        True
        >>> section["subsection"]  # No KeyError

Sections have an :meth:`~.Section.update` method allowing to modify a it with a
mapping of several parameters (or another section instance)::

    app.update({"computation.n_cores": 10, "physical.threshold": 5.})

Similarly to :meth:`~.Section.setdefault`, it can add new traits to the section
with some specific input, see the docstring for details.

.. tip::

   It is possible to only show configurable traits in autocompletion. Simply set
   :attr:`~.Section._attr_completion_only_traits` to True.


.. warning::

   Adding traits to a Section instance (via :meth:`~.Section.add_trait`,
   :meth:`~.Section.update`, or :meth:`~.Section.setdefault`) internally creates a
   new class and modifies in-place the section instance; something along
   the lines of::

       section.__class__ = type("NewClass", (section.__class__), ...)

   References to section classes necessary to operate the nested structure are
   updated accordingly, but this is a possibly dangerous operation and it would
   be preferred to set traits statically.


Obtaining subsets of all parameters
-----------------------------------

Using :meth:`.Section.select` we can select only some of the parameters by name::

  >>> app.select("physical.threshold", "computation.n_cores")
  {
      "physical.threshold": 2.5,
      "computation.n_cores": 1
  }

Some parameters may be destined for a specific function. It is possible to
select those by name as shown above, or one could tag the target traits during
definition like so::

  some_parameter = Bool(True).tag(for_this_function=True)

These traits can then automatically be retrieved using the `metadata` argument
of many methods such as :meth:`~Section.keys` or :meth:`~Section.select`.

:meth:`.Section.trait_values_from_func_signature` will find the parameters that
share the same name as arguments from a function signature.

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
not lead to a known parameter will raise errors. This allows to merge the
parameters obtained from different files and from CLI. Parameters are stored
in :attr:`~.ApplicationBase.file_conf`, :attr:`~.ApplicationBase.cli_conf`
and :attr:`~.ApplicationBase.conf`.

Finally, the application will recursively instantiate all sections while passing
the configuration values. Unspecified values will take the trait default value.
All values will undergo validation from traitlets.

The configuration values are retrieved by :class:`.ConfigLoader` objects adapted
for each source. Its output will be a **flat** dictionary mapping *resolved
keys* to a :class:`.ConfigValue`.

.. note::

   The :class:`.ConfigValue` class allows to store more information about the
   value: its provenance, the original string and parsed value if applicable,
   and a priority value used when merging configs. To obtain a value, simply use
   :meth:`.ConfigValue.get_value`.

A "resolved" key is a succession of attribute names pointing to a trait,
starting from the application. It is unique. With the same example as above for
instance: ``physical.years``.

.. important::

    It is possible to define aliases with the :attr:`.Section.aliases` attribute.
    It is a mapping of shortcut names to a deeper subsection::

        {"short": "some.deeply.nested.subsection"}

    Aliases are expanded when the configuration is resolved.

A parameter can also be input for an "orphan section", similarly to how it is
done in vanilla traitlets. It consists of the name of a section class and a
trait name: ``SomeSectionClassName.trait_name``. The section must be registered
beforehand (see :ref:`orphans`).


From configuration files
------------------------

The application can retrieve parameters from configuration files by invoking
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

File loaders can implement :meth:`.FileLoader.write` to generate a valid
configuration file of the corresponding format, following the values of present
in its :attr:`~.ConfigLoader.config` attribute. This allows to generate lengthy
configuration files, with different amounts of additional information in
comments. The end user can simply use :meth:`.ApplicationBase.write_config`
which automatically deals with an existing configuration file that may need to
be updated, while keeping its current values (or not).

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

    c.section.subesection.parameter = 5
    c.OrphanSection.parameter = True

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

`Yaml <https://yaml.org/>`__ is supported via :class:`.YamlLoader` and the
third-party module `pyyaml <https://pyyaml.org/wiki/PyYAMLDocumentation>`. It
does not allow generating input with comments (and the alternative ``ruamel``
does not seem as reliable).

Despite not being easily readable, the JSON format is also supported via
:class:`.JsonLoader` and the builtin module :external+python:mod:`json`. The
decoder and encoder class can be customized.

From the command line
---------------------

Parameters can be set from parsing command line arguments, although it can be
skipped by either setting the :attr:`.ApplicationBase.ignore_cli` trait or
the ``ignore_cli`` argument to :meth:`.ApplicationBase.start`. The configuration
obtained will be stored in the :attr:`~.ApplicationBase.cli_conf` attribute and
will take priority over parameters from configuration files.

The keys are indicated following **one or two** hyphen. Any subsequent hyphen is
replaced by an underscore. So ``-computation.n_cores`` and
``--computation.n-cores`` are equivalent. As already noted, parameters keys can
be dot-separated paths leading to a trait. Aliases can be used for brevity.
Orphan sections parameters are input with the same syntax
(``--OrphanSection.trait_name``).

.. note ::

    This can be changed with attributes of the corresponding loader class:
    :attr:`.CLILoader.allow_kebab` and :attr:`.CLILoader.prefix`.

All command line arguments need to be parsed. The corresponding trait object
will deal with the parsing, using its ``from_string`` or ``from_string_list``
(for containers) methods.

.. note::

   Nested containers parameters (list of list e.g.) are not currently supported.

.. note ::

    The list of command line arguments is obtained by
    :meth:`.ApplicationBase.get_argv`. It tries to detect if python was launched
    from IPython or Jupyter, in which case it strips the arguments before
    the first '--'.

List arguments
++++++++++++++

For any and every parameter, the argument :external+python:ref:`action` is
"append", with type :class:`str` (since the parsing is left to traitlets), and
``nargs="*"`` meaning that any parameter can receive any number of values. To
indicate multiple values, for a List trait for instance, the following syntax is
to be used::

    --physical.years 2015 2016 2017

**and not** as is the case with vanilla traitlets::

    --physical.years 2015 --physical.years 2016 ...

This will raise an error, to avoid possible mistakes in user input.

Extra parameters
++++++++++++++++

Extra parameters to the argument parser can be added with
:meth:`.ApplicationBase.add_extra_parameters`. This will add traits to a section
named "extra", created if needed. This is useful when needing a parameter for a
single script for instance. If in our script we write::

    App.add_extra_parameters(threshold=Float(5.0))

we can then pass a parameter by command line at ``--extra.threshold``.

Range Trait
+++++++++++

The packages provides a new type of trait: :class:`.RangeTrait`, which is a list
of integers, but can be parsed from a slice specification in the form
``start:stop[:step]``. So that ``--year=2002:2005`` will be parsed as ``[2002,
2003, 2004, 2005]``. Note that 'stop' is **inclusive**.


From a dictionary
-----------------

The loader :class:`.DictLoader` can transform any nested mapping into a proper
configuration. It deals in a quite straightforward manner with the issue of
differentiating between a nested mapping corresponding to an eventual trait and
one corresponding to further nesting in a subsection. It simply checks if the
key is a known subsection or alias, otherwise it assumes the key corresponds to
a parameter value.

.. note::

    The loaders :class:`.TomlkitLoader`, :class:`.YamlLoader` and
    :class:`.JsonLoader` are based on it, as they return a nested mapping.
