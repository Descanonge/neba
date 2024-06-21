
.. currentmodule:: data_assistant

###########################
Data-Asistant documentation
###########################

..

   Help manage multiple datasets when overwhelmed with many files and
   parameters.

Configuration
=============

It provides two independent modules. The first one for managing the
:doc:`configuration<configuration>` of a project, providing the means to specify
a structured, nested configuration in python code using the existing `traitlets
<https://traitlets.readthedocs.io>`__ library. This allows type-checking, value
validation and "on-change" callbacks.

The parameters values can be retrieved from configuration files (TOML, YAML,
or Python files), or from the command line.

The whole configuration can easily be documented directly inside the
specification code, and this is re-used for the command-line help, automatically
generated configuration files, and sphinx documentation with a custom autodoc
extension.

The submodule :mod:`.config.dask_config` is a show-case of using this for the
different parameters necessary when deploying Dask on a local cluster or on
distributed machines using `dask-jobqueue
<https://jobqueue.dask.org/en/latest/>`__. It also provides some convenience
start-up functions to get setup quickly.

Dataset management
==================

The second module aims to ease the creation and :doc:`management of
datasets<datasets>` with different file format, structure, etc. that can all
depend on various parameters.

Each new dataset is specified by creating a subclass of a data manager object.
Relevant attributes or methods are overridden to provide information on this
dataset. Each *instance* of this new subclass corresponds to a set of parameters
that can be used to change aspects of the dataset on the fly: choose only files
for a specific year, change the method to open data, etc.

Classes of data managers are made as universal as possible via a system of
independent plugins (kinds of mixins) that each add specific features.
One data manager can deal with multiple files data-source select via glob
patterns, loaded into pandas, while another could have a remote data-store as
input loaded into xarray.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   configuration

   datasets

.. toctree::
   :maxdepth: 3

   api

.. toctree::
   :maxdepth: 1

   extending

   motivations


Links
=====

Project home: https://gitlab.in2p3.fr/biofronts/data-assistant

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
