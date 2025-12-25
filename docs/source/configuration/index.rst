
.. currentmodule:: data_assistant

*************
Configuration
*************

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

.. toctree::
   :hidden:

   usage

   dask
