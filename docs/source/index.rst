
.. currentmodule:: neba

##################
Neba documentation
##################

A package to manage a configuration and multiple datasets.


.. grid:: 1 1 3 3

   .. grid-item-card:: Configuration framework
      :link: config
      :link-alt: configuration

      Obtain your parameters from configuration files or command line arguments.
      Validate them against a structured specification that is easy to write,
      expandable, and which allows to document every parameter.

   .. grid-item-card:: Dataset management
      :link: data
      :link-alt: dataset management

      Declare datasets in a flexible way to manage multiple source files and to
      read and write data easily using different libraries.

   .. grid-item-card:: API Reference
      :link: api
      :link-alt: API Reference

Install
=======

From PyPI::

   pip install neba

From source::

   git clone https://github.com/Descanonge/neba
   cd neba
   pip install -e .


Links
=====

Project home: https://github.com/Descanonge/neba


.. toctree::
   :maxdepth: 2
   :hidden:

   config/index

   data/index

   api/index

About
=====

Named after one of the assessors of Maat, mentioned in the book of the dead. The
deceased would have had to declare themselves innocent of various "sins" in
front of 42 assessors. Neba would judge the sin of lying.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
