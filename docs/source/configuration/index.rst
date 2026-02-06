
.. currentmodule:: neba

*************
Configuration
*************

This package provides a submodule :mod:`.config` to help managing the parameters
of a project that is:

- **strict:** parameters are defined beforehand. Any unknown or invalid
  parameter will raise errors
- **structured:** parameters can be organized in (nested) sections
- **documented:** docstrings of parameters are re-used in configuration files,
  command line help, and static documentation via a plugin for Sphinx

The parameters values can be recovered from configuration files (TOML, YAML,
Python files, or JSON), and from the command line as well.

It requires to specify the parameters in python code: their type,
default value, help string, etc. It relies on the `traitlets
<https://traitlets.readthedocs.io>`__ package to do this.

.. note::

   The main difference with the "vanilla" traitlets package is that we allow
   nested configurations. We replace :class:`traitlets.config.Configurable` by
   our subclass :class:`~config.section.Section` and use our own
   :class:`~config.application.ApplicationBase` class.

The help string of each trait is used to generate command line help, fully
documented configuration files, and the :mod:`.autodoc_trait` plugin integrates
it in sphinx documentations.

.. toctree::
   :hidden:

   usage

   extending
