
.. currentmodule:: data_assistant.data

******************
Dataset management
******************

This package has a submodule :mod:`~data_assistant.data` to ease the creation
and management of multiple dataset with different file format, structure, etc.
that can all depend on various parameters. Each new dataset is specified by
creating a new subclass of :class:`~.Dataset`. It contains
interchangeable *modules* that each cover some functionalities.

If each Dataset subclass specifies access to some data, and each *instance* of
that subclass corresponds to a set of parameters that can be used to change
aspects of the dataset on the fly: choose only some files for a specific year,
change the method to open data, etc.


.. toctree::
   :hidden:

   usage

   existing_modules
