
******************
Design motivations
******************

Here is a small exploration on the choices made for this package: the how and
why. Some tools in this package can seem (or are) quite complex, so I hope to
provide some justification on why it is so.

A good configuration framework
==============================

.. currentmodule:: data_assistant.config

Requirements
------------

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

Existing libraries
------------------

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

Choosing traitlets
------------------

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

Main idea
---------

The :mod:`data_assistant.data` submodule stems from the need of managing many
different datasets, sufficiently similar in their structure to try to automatize
things, but with enough specificities to make it difficult.

The defining idea is to create a class for each new dataset. Instances of that
class will correspond to different versions of that datasets, depending on the
value of some parameters for instance.
As for the Sections, the class definition syntax is clear, provide clear
inheritance, and allows to overwrite existing logic to account for the dataset
specificities.

For instance, we could have a parent dataset class that contains all the logic
for dealing loading multiple files using the Xarray library, and multiple child
datasets that specify where to find the files, add post-processing, etc::

    class ParentDataset:

        # all the logic to load data
        ...

    class CHL_Dataset(ParentDataset):

        def get_files(self):
            # overwrites the location of files
            return "where the CHL files are"

    class SST_Dataset(ParentDataset):

        def get_files(self):
            return "where the SST files are"

        def postprocessing(self):
            # add some post-processing for SST
            self.data -= 273.15

I though that if I was to implement such a thing, it would be more interesting
to make it re-usable and flexible. That it could take different kind of source
as input (a file, multiple files, a data store, etc.), load and/or write the
data with different libraries (numpy, xarray, pandas, etc.).

Using inheritance
-----------------

The first version using multiple inheritance, the current modules being instead
mixins. The main advantage is a very simple syntax: all the methods are in one
big dataset object, so overwriting them in a subclass is a succinct and very
clear. It did not reach too complicated inheritance yet, so the inheritance was
relatively clear to grasp for a user, and static type checking worked very well.
Mixin interplay was very simple: just make a new mixin inheriting two or more
mixins.

However I started to reach some heavy cons. Having many plugins can clutter the
namespace and lead to name clashes. Using a static type-checker should prevent
most mistakes though. Maybe most notably, mixins are great to add methods, but
adding attributes is more complicated. All plugin attributes are shared and
separating them automatically is difficult since it is not possible to know at
runtime in "whose" plugin code we are. Using caches was a difficult task and
required hard-coding a lot of things.

Some inheritance was getting quite hairy, especially on the writer side, and it
seemed to me that composition could simplify things quite a bit.

Lastly, because we can only manipulate a sinle data-manager object, not
individual parts of it, it is impossible to dynamically combine different
plugins. I found myself needing two different ways to find files (a dataset
split into two completely different parts). It feels wrong to not be able to
solve such an easy problem, and might hint at further difficulties.

Using composition
-----------------

Composition was not used at first because I found the process of definition
complicated: the user would need to subclass each modules, subclass the data
manager and assign the new module types.

Another method (the actual first one tried) was to have the modules keep a
reference of their parent dataset, and call methods bound to that dataset. The
user could define or overwrite methods directly on the dataset and it would
affect the behavior of modules. However, having tried this approach, despite
working fairly well, it seems quite confusing for the end user. Expressing
clearly and in a strict manner to the user what methods and attributes to define
on the dataset is not trivial. This also confuses static type-checkers.

After developping the whole thing using inheritance, and having worked a lot on
the configuration side, I had a better grasp of the class definition process and
how to alter it dynamically. This prompted me to turn to composition, and making
the definition of new datasets quicker by using dynamic definition (with
``__init_subclass__``).
