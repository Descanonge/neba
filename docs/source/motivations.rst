
******************
Design motivations
******************

Here is a small exploration on the choices made for this package: the how and
why. Some tools in this package can seem (or are) quite complex, so I hope to
provide some justification on why it is so.

A good configuration framework
==============================

.. currentmodule:: data_assistant.config

Let's starts with the :doc:`configuration` side of things. This library had some
requirements from the start:

* a strict specification of the parameters (name, type, etc.)
* that can easily be documented (even "self-documented")
* that can easily be written
* that can read from configuration file(s) and command line arguments

It seems evident that knowing what each parameters should be, and how to use
them helps to understand the project code. I would argue that it is especially
important to facilitate this for scientific projects that are not necessarily
written by seasoned developers, and that may not contain extensive documentation
otherwise. Nevertheless, we should strive to make scientific code that can
easily be understood, replicated, extended.

Configuration files are important to for replication, and it is often useful
to be able to overwrite some parameters on the command line to launch batch
scripts for instance.

There are many existing configuration frameworks (and feature-adjacent tools)
that could be considered: `OmegaConf <https://omegaconf.readthedocs.io/en>`__,
`Hydra <https://hydra.cc/>`__, `Dynaconf <https://www.dynaconf.com/>`__,
`GinConfig <https://github.com/google/gin-config>`__, `ConfigArgParse
<https://github.com/bw2/ConfigArgParse>`__, and probably many more that I don't
know about or have forgotten.

Sadly, I don't consider that any one of them really ticks all the boxes. The
alternative is thus to start from one of them and add the missing features. I
strongly considered OmegaConf, seeing that it was highly flexible. However, I
found the syntax for strict `"structured configs"
<https://omegaconf.readthedocs.io/en/latest/structured_config.html>`__ to be a
bit tedious for compound types (needing a factory function), and no easy way to
retrieve documentation at runtime.

That is why I chose to expand on another library: `traitlets
<https://traitlets.readthedocs.io>`__. It may very well be already present in
your Python environment, as it is the library used to configure `IPython
<https://ipython.readthedocs.io/>`__ and other Jupyter applications. It uses a
similar tool as OmegaConf (*ie* descriptors called traits) but more advanced,
allowing further customization and access to all the metadata at runtime. Traits
also already implement type validation and parsing, two very challenging aspects
of such a library, as well as many other advanced features and advantages like
callbacks on parameter change, dynamic default values, cross-validation, etc.
Traitlets also deals quite elegantly with subclassing the configuration objects.

Traitlets is meant for application developers, but it could be turned into a
simple configuration framework for end-users with some boilerplate code. One of
the drawback of traitlets however is its unability to deal with nested
configurations. This is minor, but I feel that modern configuration formats and
frameworks make use of it, and that not supporting it could draw users away. I
thus set on adapting traitlets for a nested configuration, as well as having a
more centralized configuration. This side of the project might have turned into
a big sunken cost fallacy to achieve this goal. Still, I hope the arguments
advanced above justify the effort.

Some parts have been re-written nearly from scratch, like the
:class:`traitlets.config.Application` and the loading (from file or CLI) that
were too incompatible with the end goal. But a large portion of it was taken or
inspired from traitlets code. Furthermore, the :class:`~traitlets.TraitType`
itself already holds a lot of functionality that does not have to be rewritten.
Nonetheless, this gave me more control on the end result, like the centralized
configuration and the overall end-user experience, that I hope will be simpler
to use. Likewise, (re)writing the :class:`~.config.loader.ConfigLoader` allowed
to quickly setup loading from new formats (TOML, soon Yaml) and generating
configuration files with fine control.


Dealing with many datasets
==========================

.. currentmodule:: data_assistant.data
