
.. currentmodule:: neba.config


*****
Usage
*****

This page details how to use the configuration framework of Neba.

Specifying parameters
=====================

To use the configuration framework, you must first define your configuration
in Python. Here is an example of how it will look::

    from neba.config import Application, Section
    from traitlets import Bool, Float, Int, List, Unicode


    class App(Application):

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

Traits
------

The configuration is specified through :class:`~.section.Section` classes. Each
section contains parameters in the form of class attribute of type
:class:`traitlets.TraitType` (for instance :class:`~traitlets.Float`,
:class:`~traitlets.Unicode`, or :class:`~traitlets.List`).

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

   It behaves *nearly* like a normal float attribute. When we change the value
   for instance, the trait (again which is a *class attribute*) will be used
   to validate the new value, or do some more advanced things. But the value
   remains tied to the container instance ``c``.

Here are some of the basic traits types:

+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Int`,     |                                                  |
| :class:`~traitlets.Float`,   |                                                  |
| :class:`~traitlets.Bool`     |                                                  |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Unicode`  | For strings (Traitlets                           |
|                              | differentiates unicode and bytes                 |
|                              | strings).                                        |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.List`,    | Containers *can* check the                       |
| :class:`~traitlets.Set`,     | element type: ``List(Float())``, or not:         |
|                              | ``List()``.                                      |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Tuple`    | Tuples are fixed length. To check the types of   |
|                              | its elements, you *must* specify every element:  |
|                              | ``Tuple(Int(), Unicode())``                      |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Dict`     | Dict can specify either keys and values:         |
|                              | ``Dict(key_trait=Unicode(), value_trait=Int())`` |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Enum`     | Must be one of the specified values:             |
|                              | ``Enum(["a", "b"], default_value="a")``          |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Union`    | Multiple types are permitted. Will try to        |
|                              | convert values in the order types are specified  |
|                              | until it succeds.                                |
|                              | For instance, prefer this order:                 |
|                              | ``Union([Int(), Float()]``, otherwise integers   |
|                              | will always be converted to floats.              |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Type`     | ``Type(klass=MyClass)`` will allow subclasses    |
|                              | of MyClass. In your configuration files you can  |
|                              | use an import string ("my_module.MyClass").      |
+------------------------------+--------------------------------------------------+
| :class:`~traitlets.Instance` | This is currently unsupported.                   |
+------------------------------+--------------------------------------------------+

Neba provides two new of types traits. :class:`.RangeTrait` is a list of
integers or floats that can be parsed from a slice specification of the form
``start:stop[:step]``. 'stop' is **inclusive**. It can still take in lists of
values normally (``--year 2002 2005 2006``).

* With ``year = RangeTrait(Int())``, ``--year=2002:2004`` will be parsed as
  ``[2002, 2003, 2004]``
* With ``coef = RangeTrait(Float())``, ``--coef=0:1:0.5`` will be parsed as
  ``[0.0, 0.5, 1.0]``.

To get a descending list, change the order of start and stop:
``--year=2008:2002:4`` will be parsed as ``[2008, 2004]``.

:class:`.FixableTrait` is meant to work with `filefinder
<https://filefinder.readthedocs.io/>`__, for parameters defined in filename
patterns. It can take

* a single value
* a string that will be interpreted as a range of values if the trait type
  allows it (Int or Float)
* a string that will be interpreted as a regular expression (this is disabled by
  default as it can be dangerous: any value from the command line that cannot be
  parsed would still be allowed).
* a list of values


Subsections
-----------

A section can contain other sub-sections, allowing a tree-like, nested
configuration. It can be done by in two ways:

* Subsections can be defined directly inside another section class definition.
  The name of the nested class will be used to access the subsection and its
  traits. The class definition will be renamed and moved under the attribute
  ``_{name}SectionDef``. For example::

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

  A mypy plugin is provided to support these dynamic definitions. Add it to the
  list of plugins in your mypy configuration file, for instance in
  '*pyproject.toml*'::

    [mypy]
    plugins = ['neba.config.mypy_plugin']

* A more standard way is by using the :class:`~section.Subsection` class
  and setting it as an attribute in the parent section::

    from neba.config import Subsection

    class ChildSection(Section):
        b = Int(2)

    class ParentSection(Section):
        a = Int(1)

        child = Subsection(ChildSection)

    >>> sec = ParentSection()
    >>> sec.a
    1
    >>> sec.child.b
    2

.. Note::

   Like traits, Subsections are also descriptors: accessing from an instance
   will give the subsection instance (``sec.child`` is a ChildSection instance),
   and accessing from a class will give a :class:`.Subsection` object which
   contains information about the subsection type (``ParentSection.child.klass
   is ChildSection``).



Aliases
-------

It is possible to define aliases with the :attr:`.Section.aliases` attribute.
It is a mapping of shortcut names to a deeper subsection::

    {"short": "some.deeply.nested.subsection"}


Application
===========

The principal section, at the root of the configuration tree, is the
:class:`Application<.application.Application>`. As a subclass of
:class:`~.Section`, it can hold directly all your parameters and nested
subsections. It will also be responsible for gathering the parameters from
configuration files and the command line, and more.

Starting the application
------------------------

By default, when the application is instantiated it executes its starting
sequence with the :meth:`~.Application.start` method. It will:

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

Logging
-------

The base application contains some parameters to easily log information. A
logger instance is available at :attr:`.Application.log` that will log to the
console (stderr), and can be configured via the (trait) parameters
:attr:`~.Application.log_level`, :attr:`~.Application.log_format`, and
:attr:`~.Application.log_datefmt`.

The configuration of the logging setup is kept minimal. Users needing to
configure it further may look into :meth:`.Application._get_logging_config`.

.. note::

   The logger will have the application class fullname (module + class name), so
   logging inheritance rules will apply.

Accessing parameters
====================

As explained :ref:`above<traits-explain>`, the **value** of parameters can be
accessed (or changed) just like attributes of the section that contains them.
This allows for deeply nested access::

  app.some.deeply.nested.trait = 2

.. tip::

   It is possible to only show subsections and configurable traits in
   autocompletion. Set the class attribute
   :attr:`.Section._attr_completion_only_traits` to True.

Sections also implements the interface of a
:class:`~collections.abc.MutableMapping` and most of the interface of a
:class:`dict`. Parameters can be accessed with a single key of dot-separated
attributes. This still benefits from all features of traitlets. ::

  app["some.deeply.nested.trait"] = 2
  # or
  app["some"]["deeply.nested.trait"] = 2

By default :meth:`.Section.keys`, :meth:`.Section.values` and
:meth:`.Section.items` do not list subsections objects or aliases, but this
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

Sections have an :meth:`~.Section.update` method allowing to modify it with a
mapping of several parameters (or another section instance)::

    app.update({"computation.n_cores": 10, "physical.threshold": 5.})

Similarly to :meth:`.Section.setdefault`, it can add new traits to the section
with some specific input, see the docstring for details.

.. warning::

   Adding traits to a Section instance (via :meth:`~.Section.add_trait`,
   :meth:`~.Section.update`, or :meth:`~.Section.setdefault`) internally creates a
   new class and modifies in-place the section instance; something along
   the lines of::

       section.__class__ = type("NewClass", (section.__class__), ...)

   References to section classes necessary to operate the nested structure are
   updated accordingly, but this is a possibly dangerous operation and it would
   be preferred to set traits statically.

.. note::

    When changing the value of a trait (with any method), traitlets will
    validate the new value and trigger callbacks if registered. Refer to the
    :external+traitlets:doc:`traitlets documentation<using_traitlets>` for more
    details on how to use these features.


Obtaining subsets of all parameters
-----------------------------------

We can select only some of the parameters by name by using
:meth:`~.Section.select`::

  >>> app.select("physical.threshold", "computation.n_cores")
  {
      "physical.threshold": 2.5,
      "computation.n_cores": 1
  }

Each trait can be tagged. This can be used to group traits together. For
instance if we tag some traits with::

  some_parameter = Bool(True).tag(group_a=True)

we can recover them all accross the configuration by using the `metadata`
argument in many methods such as :meth:`~.Section.keys` or
:meth:`~.Section.select` (``app.select(group_a=True)``).
Use :func:`@tag_all_traits<.tag_all_traits>` to tag all traits of a section::

    class App(Application):

        @tag_all_traits(group_a=True)
        class subsection(Section):
            a = Int(0)
            b = Int(1).tag(group_a=False)  # will not be tagged as True

If some traits are meant to be used as arguments to a specific function,
:meth:`~.Section.trait_values_from_func_signature` will find the parameters that
share the same name as arguments from a function signature.

Input parameters
================

The :class:`.Application` class allows to retrieve the values of parameters from
configuration files or from command line arguments (CLI), when
:meth:`.Application.start` is launched. It first parses command line arguments
(unless deactivated) and then reads values from specified configuration files.
Each time parameters are loaded from any kind of source, the parameters for the
application object are immediately applied to it, since they can alter the rest
of the process.

The configuration values are retrieved by :class:`.ConfigLoader` objects adapted
for each source. Its output will be a **flat** dictionary mapping keys to a
:class:`.ConfigValue`. Aliases are expanded so that each key is unique.

.. note::

   The :class:`.ConfigValue` class allows to store more information about the
   value: its origin, the original string and parsed value if applicable, and a
   priority value used when merging configs. To obtain the value, use
   :meth:`.ConfigValue.get_value`.

Parameters obtained from configuration files and from CLI are merged. Parameters
are stored in :attr:`~.Application.file_conf`, :attr:`~.Application.cli_conf`
and :attr:`~.Application.conf`.

Finally, the application will recursively instantiate all sections while passing
the configuration values. Unspecified values will take the trait default value.
All values will undergo validation from traitlets.

.. important::

    By default, all this process is automatic, to use your application you only
    have to instantiate your application::

        class App(Application):
            ...

        app = App()
        app.my_parameter  # retrieved from config files or CLI

From configuration files
------------------------

The application can retrieve parameters from configuration files by invoking
:meth:`.Application.load_config_files`. It will load the file (or files)
specified in :attr:`.Application.config_files`. If multiple files are specified,
the parameter from one file will replace those from the previous files in the
list. The resulting configuration will be stored in the
:attr:`~.Application.file_conf` attribute.

.. note::

   The :attr:`~.Application.config_files` attribute is a trait, which allows to
   select configuration files from the command line. To specify it from your
   script use::

       class App(Application):
           pass

       App.config_files.default_value = ...

   or if you do not need to change the value using command line arguments::

       class App(Application):
           config_files = ...


Different file formats require specific subclasses of :class:`~.FileLoader`. A
loader is selected by looking at the config file extension. As some loaders have
external dependencies, loaders are only imported when needed, according to the
import string in :attr:`.Application.file_loaders`.

+-----------------+------------------------------+----------+
| File extensions | Class                        | Library  |
+=================+==============================+==========+
| toml            | :class:`.toml.TomlkitLoader` | tomlkit_ |
+-----------------+------------------------------+----------+
| py, ipy         | :class:`.python.PyLoader`    |          |
+-----------------+------------------------------+----------+
| yaml, yml       | :class:`.yaml.YamlLoader`    | ruamel_  |
+-----------------+------------------------------+----------+
| json            | :class:`.json.JsonLoader`    | json_    |
+-----------------+------------------------------+----------+

.. _tomlkit: https://pypi.org/project/tomlkit/
.. _ruamel: https://yaml.dev/doc/ruamel.yaml/
.. _json: https://docs.python.org/3/library/json.html

File loaders can implement :meth:`.FileLoader.write` to generate a valid
configuration file of the corresponding format, following the values present in
its :attr:`~.ConfigLoader.config` attribute. This allows to generate lengthy
configuration files, with different amounts of additional information in
comments. The end user can simply use :meth:`.Application.write_config` which
automatically deals with an existing configuration file that may need to be
updated, keeping its current values (or not).

Neba supports and **recommends** `TOML <https://toml.io>`__ configuration
files. It is both easily readable and unambiguous. Despite allowing nested
configuration, it can be written without indentation, allowing to add long
comments for each parameters. The :external+python:mod:`tomllib` builtin module
does not support writing, so we use (for both reading and writing) one of the
recommended replacement: `tomlkit <https://pypi.org/project/tomlkit>`__.

The package also support python scripts as configuration files, similarly to how
traitlets is doing it. To load a configuration file, the file loader creates a
:class:`.PyConfigContainer` object. That object will be bound to the ``c``
variable in the script/configuration file. It allows setting nested attribute so
that the following syntax is valid::

    c.section.subsection.parameter = 5

.. important::

    Remember that this script will be **executed**, so arbitrary code can be run
    inside, maybe changing some value depending on the OS, the hostname, or more
    advanced logic.

    Of course running arbitrary code dynamically is a security liability, do not
    load parameters from a python script unless you trust it.

The loader does not support the traitlets feature of configuration file
inheritance via (in the config file) ``load_subconfig("some_other_script.py")``.
This would be doable, but for the moment we recommend instead that you specify
multiple configuration files in :attr:`.Application.config_files`, remembering
that each configuration file replaces the values of the previous one in the
list.

`Yaml <https://yaml.org/>`__ is supported via :class:`.YamlLoader` and the
third-party module `ruamel.ymal <ruamel_>`_.

Despite not being easily readable, the JSON format is also supported via
:class:`.JsonLoader` and the builtin module :external+python:mod:`json`. The
decoder and encoder class can be customized.

From the command line
---------------------

Parameters can be set from parsing command line arguments, although it can be
skipped by either setting the :attr:`.Application.ignore_cli` attribute or the
``ignore_cli`` argument to :meth:`.Application.start`. The configuration
obtained will be stored in the :attr:`~.Application.cli_conf` attribute and will
take priority over parameters from configuration files.

The keys are indicated following **one or two** hyphen. Any subsequent hyphen is
replaced by an underscore. So ``-computation.n_cores`` and
``--computation.n-cores`` are equivalent. Parameters keys are dot-separated
paths leading to a trait. Aliases can be used for brevity.

.. note ::

    This can be changed with attributes of the corresponding loader class:
    :attr:`.CLILoader.allow_kebab` and :attr:`.CLILoader.prefix`.

Command line arguments need to be parsed. The corresponding trait object
will deal with the parsing, using its ``from_string`` or ``from_string_list``
(for containers) methods.

.. note::

   Nested containers parameters (list of list e.g.) are not currently supported.

.. note ::

    The list of command line arguments is obtained by
    :meth:`.Application.get_argv`. It tries to detect if python was launched
    from IPython or Jupyter, in which case it ignores the arguments before the
    first ``--``.

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

This will raise an error since duplicates are forbidden to avoid possible
mistakes in user input.

Extra parameters
++++++++++++++++

Extra parameters to the argument parser can be added with the class method :meth:`.Application.add_extra_parameters`. This will add traits to a section
named "extra", created if needed. This is useful when needing parameters for a
single script for instance. If in our script we write::

    App.add_extra_parameters(threshold=Float(5.0))

we can then pass a parameter from the command line with ``--extra.threshold``
and retrieve it with ``app.extra.threshold``.

Autocompletion
++++++++++++++

Autocompletion for parameters is available via `argcomplete
<https://github.com/kislyuk/argcomplete>`__. Install argcomplete and either
register the scripts you need or activate global completion. In both cases you
will need to add ``# PYTHON_ARGCOMPLETE_OK`` to the beginning of your scripts.

.. note::

    Completion is not available when using ipython, as it shadows our application.
    I do not know if this is fixable.


From a dictionary
-----------------

The loader :class:`.DictLoader` can transform any nested mapping into a proper
configuration.

.. note::

    The loaders :class:`.TomlkitLoader`, :class:`.YamlLoader` and
    :class:`.JsonLoader` are based on it, as they return a nested mapping.
