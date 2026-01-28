
.. currentmodule:: data_assistant.data

******************
Dataset management
******************

This package has a submodule :mod:`~data_assistant.data` to ease the creation
and management of multiple dataset with different file format, structure, etc.
that can all depend on various parameters. Each new dataset is specified by
creating a new subclass of :class:`~.Dataset`. It contains
interchangeable *modules* that each cover some functionalities.

Classes of data managers are made as universal as possible via a system of
modules that each cover specific features, and whose implementation can be
changed between datasets. One data manager can deal with multiple source files
selected via glob patterns, loaded into pandas, while another could
have a remote data-store as input loaded into xarray.


.. toctree::
   :hidden:

   usage

   existing_modules
