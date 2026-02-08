
***********************
Autodoc_trait extension
***********************

Neba provides a Sphinx extension to automatically document your configuration.
Add the extension to your sphinx configuration (in ``conf.py``):

.. code-block:: py

    extensions = [
        ...,
        "neba.autodoc_trait",
    ]

This adds a new autodoc directive for sections (and applications):

.. code-block:: rst

    .. autosection:: my_module.MySection

It will list traits from all subsections. It will not document any other attribute or
methods.

.. note::

    This uses the legacy autodoc implementation but it does not require you to activate
    it in your configuration.


Options
=======

Other autodoc options apply, but not all may work.

.. rst:directive:option:: inherited-members
    :type: comma separated list

    Works the same as for autodoc. If present, document traits the section inherits from
    parent classes. If a comma separated list, do not document traits inherited from
    those classes.

.. rst:directive:option:: member-order
    :type: alphabetical, bysource or traits-first

    * ``alphabetical``: Sort every trait and section in alphabetical order.
    * ``bysource``: Keep the order from the source files.
    * ``traits-first``: Keep the order from the source files, but put the traits of a
      section before its subsections.

.. rst:directive:option:: only-configurables
    :type:

    Only document configurable traits.

A good default is

.. code-block:: rst

    .. autosection:: my_module.MySection
        :inherited-members: Configurable
        :member-order: bysource
        :only-configurables:


Example
=======

If we use it to document :class:`.ApplicationBase`:

.. autosection:: neba.config.application.ApplicationBase
    :inherited-members: Configurable
    :member-order: bysource
    :only-configurables:
