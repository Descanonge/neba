
.. currentmodule:: neba

**************************
Extending and going beyond
**************************

Below are listed expected ways to customize the configuration side package of
Neba, as well as existing ideas to develop further this library. In any case,
feel free to reach out if you feel some features are missing, not working as you
would expect them to, or if you have trouble extending it yourself.

Section
=======

The building block of the nested configuration is the :class:`.Section` class.
It holds crucial parts of the configuration framework, notably the methods to
resolve keys. Using a subclass instead when creating your configuration should
be enough to customize the behavior of the sections. Some functions (like
:meth:`.Section.update` or :meth:`.Application.add_extra_parameters`)
automatically create empty Section objects whose type is currently hard-coded.

Application
===========

One can overwrite the methods: :meth:`~.Application.start` to change the general
workflow, :meth:`~.Application._create_cli_loader` and
:meth:`~.Application.get_argv` to change command line parsing. The attribute
:attr:`~.Application.file_loaders` contains the configuration loaders to be used
for config files that can each be replaced.

Orphan keys
-----------

A limitation of the framework is that all the sections classes *must* be
imported at runtime. If not, any key referencing a section that is not imported
will raise an error (as intended). However, it could be desirable to have parts
of the configuration lazily loaded while avoiding errors (for instance sections
that are specific to a dataset, or a script).

"Orphan keys" were implemented as some point to solve this issue. The user would
list in the application a list of orphan Sections (just their class-name or
their full import-string). Orphan keys would start from a class-name
("ClassName.my_trait").

Implementing it fully brings some difficulties though: it would part the
configuration in two: the configuration tree, and the orphan classes. The whole
configuration side is impacted.

Generic config type
-------------------

Currently, the configurations obtained from file
(:attr:`.Application.file_conf`) or command line arguments
(:attr:`.Application.cli_conf`) are stored as :class:`dict` mapping keys
(strings with dot to indicate nesting) to :class:`.ConfigValue`.

It could possibly be replaced by other types of containers, such as `Box
<https://github.com/cdgriffith/Box>`__ or an OmegaConf object to enable easier
interfacing. This idea is still quite vague though.

Config loaders
==============

More file formats
-----------------

The :class:`.ConfigLoader` class has been made to be easily customized to work
for parsing command line and different types of file formats. For the later,
adding formats is quite easy and it should suffice to implement
:meth:`.ConfigLoader.load_config`. To generate configuration files in this
format, there only need to implement :meth:`.FileLoader._to_lines`. Existing
classes in :mod:`.config.loaders` can serve as examples.

.. important::

    Any additional file loader class should be added to
    :attr:`.Application.file_loaders` to be utilized by the application.

Parameter interpolation
-----------------------

A missing feature of this framework, that could be considered an important one,
is referencing a parameter when specifying another. OmegaConf calls it
:external+omegaconf:ref:`interpolation`.

A first, simple implementation seems feasible. After loading configuration, we
have a flat, fully resolved configuration. Before instantiating the sections, it
should be possible to apply interpolation: any value that is a string could be
examined and if mention of another parameter is made, it could be replaced.
Circle referencing should be checked.

The :external+omegaconf:doc:`custom_resolvers` feature of OmegaConf seems useful
as well, though its implementation appears more complex. The idea of being able
to indicate a deprecated parameter is especially seducing (not necessarily
through interpolation, but maybe using traits metadata).

However, traitlets already possess extensive event processing abilities, such as
:external+traitlets:func:`traitlets.observe` that transforms a method into a
hook that is run whenever a specific traits is changed. This can cover those use
cases, maybe in a more roundabout way, but with probably more flexibility.
