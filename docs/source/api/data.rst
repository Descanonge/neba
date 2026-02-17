
****
data
****

.. automodule:: neba.data

.. currentmodule:: neba.data

Contents
========

.. rubric:: Dataset and modules
.. autosummary::
   :nosignatures:

   ~module.autocached
   ~module.Module
   ~module.CachedModule
   ~dataset.Dataset
   ~dataset.DatasetSection
   ~store.DatasetStore

.. rubric:: Parameters
.. autosummary::
   :nosignatures:

   ~params.ParametersAbstract
   ~params.ParametersApp
   ~params.ParametersDict
   ~params.ParametersSection


.. rubric:: Source
.. autosummary::
   :nosignatures:

   ~source.SourceAbstract
   ~source.SimpleSource

   ~source.MultiFileSource
   ~source.FileFinderSource
   ~source.GlobSource

   ~source.SourceIntersection
   ~source.SourceUnion

.. rubric:: Loader
.. autosummary::
   :nosignatures:

   ~loader.LoaderAbstract

.. rubric:: Writer
.. autosummary::
   :nosignatures:

   ~writer.SplitWriterMixin
   ~writer.Splitable
   ~writer.WriterAbstract


Modules
=======

.. autosummary::
   :toctree: _generated
   :nosignatures:
   :recursive:

   dataset
   loader
   module
   params
   source
   store
   types
   writer
   xarray
