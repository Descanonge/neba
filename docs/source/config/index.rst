
.. currentmodule:: neba

*************
Configuration
*************

Neba offers a configuration framework that is:

- **strict:** parameters are defined beforehand in Python code. Any unknown or
  invalid parameter will raise errors.
- **structured:** parameters can be organized in (nested) sections.
- **documented:** docstrings of parameters are re-used in configuration files,
  command line help, and static documentation via a Sphinx extension.

The parameters values can be recovered from configuration files (TOML, YAML,
Python files, or JSON) and from the command line.


.. note::

    Neba is based on the `traitlets <https://traitlets.readthedocs.io>`__
    package. The main difference is that Neba allows nested configurations. To
    do that, it replace the :class:`traitlets.config.Configurable` class with
    :class:`~config.section.Section` and uses its own
    :class:`~config.application.ApplicationBase` class. The objects reading the
    configuration from files and command line arguments have also been rewritten
    and expanded.


.. toctree::
   :hidden:

   usage

   extending

   autodoc_trait
