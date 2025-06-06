
.. currentmodule:: data_assistant

**************************
Extending and going beyond
**************************

This whole package was created with extension in mind, since every use case is
different and users might want to customize parts of it. On the one hand, the
dataset specification in :mod:`.data` has flexibility integrated in its
structure with individual modules, so little is to be added on this side. On the
other hand, they are possible avenues of customization and extensions of current
features for the :mod:`.config` submodule that may not be obvious.

Below are listed expected ways to customize this package, as well as existing
ideas to develop further this library. In any case, feel free to reach out if
you feel some features are missing, not working as you would expect them to, or
if you have trouble extending it yourself.

Section
=======

The building block of the nested configuration is the :class:`.Section` class.
It holds crucial parts of the configuration framework, notably the methods to
resolve keys.

Using a subclass instead when creating your configuration should be enough to
customize the behavior of the sections.

To go further, it could be possible (did not thoroughly checked) to replace it
by another class entirely that would only implement some basic features. Most of
the other elements of the framework rely on methods inherited from
:class:`traitlets.config.Configurable` and the basic attribute
:attr:`.Section._subsections`. This could constitute a base protocol for sections.


Application
===========

The application is the main entry point for the configuration framework,
orchestrating the loading of parameters, and holding the configuration tree.
Using a subclass that overwrites some methods is expected, such as
:meth:`~.ApplicationBase.start` to change the general workflow,
:meth:`~.ApplicationBase._create_cli_loader` and
:meth:`~.ApplicationBase.get_argv` to change the command line parsing, The
attribute :attr:`~.ApplicationBase.file_loaders` containing the configuration
loaders to be used for config files is also important.

To go even further, one could create their own application base class starting
from scratch.

We pondered the eventuality of using a different (sub)class of :class:`.Section`
previously, which is itself the parent class of the application. As it is
hard-coded, it is currently impossible to use a different section base for the
application, but maybe that could somehow be changed?

Orphan keys
-----------

A limitation of the framework is that all the sections classes *must* be imported
at runtime. If not, any key referencing a section that is not imported will raise
an error (as intended). However, it could be desirable to have part of the
configuration lazily loaded while avoiding errors.

.. note::

    Currently this can be done by disabling strict parsing all-together.

A simple way to solve this problem is the use of what I would call "orphan
keys". Instead of being part of the configuration tree, these keys would be
class-keys referencing a previously registered Section (or Configurable even).
Because it relies only on class-keys, we only need to indicate the name of those
expected class to not raise any errors. It would part the configuration in two
though: the configuration tree, and the orphan classes.

A slightly more ambitious project could be to provide similar functionality not
for isolated classes, but for entire parts of the configuration tree. But the
importance of the use cases where it would prove useful or needed still has to
be proven.

Generic config type
-------------------

Currently, the configurations obtained from file
(:attr:`.ApplicationBase.file_conf`) or command line arguments
(:attr:`.ApplicationBase.cli_conf`) are stored as :class:`dict` mapping keys
(strings with dot to indicate nesting) to :class:`.ConfigValue`.

It could possibly be replaced by other types of containers, such as `Box
<https://github.com/cdgriffith/Box>`__ or an OmegaConf object to enable easier
interfacing. This idea is still quite vague though.

Config loaders
==============

More file formats
-----------------

Again the :class:`.ConfigLoader` class has been made to be easily customized to
work for parsing command line and different types of file formats. For the
latter, adding formats is quite easy and it should suffice to implement
:meth:`.ConfigLoader.load_config`. If there is a need to generate configuration
files in this format there also is only need to implement
:meth:`.FileLoader._to_lines`. Existing classes in :mod:`.config.loaders` can
serve as examples.

.. important::

    Any additional file loader class should be added to
    :attr:`.ApplicationBase.file_loaders` to be utilized by the application.

Command line completion
-----------------------

Traitlets allowed completion at the command line of the existing configurable
classes and the traits therein.

Inspiration could be taken from their implementation to enable this feature. We
already have :meth:`.Section.keys` that provides an example on how to list
sub-sections and their parameters, as well as aliases.

Parameter interpolation
-----------------------

A missing feature of our framework, that could be considered an important one,
is referencing a parameter when specifying another. OmegaConf calls it
:external+omegaconf:ref:`interpolation`.

A first, simple implementation seems feasible. After loading configuration, we
have a flat, fully resolved configuration. Before instantiating the sections, it
should be possible to apply interpolation: any value that is a string could be
examined and if mention of another parameter is made, it could be replaced.
Circle referencing should be checked.

The :external+omegaconf:doc:`custom_resolvers` feature of OmegaConf seems useful
as well, even though its implementation appears more complex. The idea of being
able to indicate a deprecated parameter is especially seducing (not necessarily
through interpolation, but maybe using traits metadata).

However, traitlets already possess extensive event processing abilities, such as
:external+traitlets:func:`traitlets.observe` that transform a method into a
hook that is run whenever a specific traits is changed. This can cover the use
cases, maybe in a more roundabout way, but with it seems great flexibility.

Data manager and modules
========================

As already stated, data managers are meant to be flexible and accommodate any
source and data type. I can only recommend to look at the implementation of
existing modules such as for multi-files sources (:mod:`.data.source`) or for
XArray loading and writing (:mod:`.data.xarray`).

You can notice that in the former, the filefinder packacge is only lazily loaded
inside a bound method (:meth:`.FileFinderSource.filefinder`), so that users that
do not use it are not required to install it or import it. For the same reasons,
for XArray all module were put in their own submodule that is not imported by
default.

Strict parameters module
------------------------

An idea of parameter management module is of one that would check that all
required parameters (specified as a class attribute) are present. It could also
only keep required parameters and discard others. It would make the most sense
for the :class:`.ParamsManager` plugin but could be easily made to work
with any kind of parameters storage that implement. However the existing
:class:`.ParamsManagerSection` somewhat fills this requirement.

Completely different DataManager
--------------------------------

The process of defining module quickly inside a data-manager class definition
could be re-used for other purposes. Or maybe the chosen default modules
(parameters, source, loader, writer) is not appropriate. Modules can be easily
replaced or even added, but someone could want something completely different.
They could then create their own data-manage base class from
:class:`.HasModules` which is the parent class that implements the module
discovery and initialization.

The :class:`.Module` class is still very much expecting to be in a
:class:`.DataManagerBase` to ease the development. A solution could be found to
make Module and HasModules more easily re-usable.
