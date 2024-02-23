# data-assistant

> Help manage multiple datasets when overwhelmed with many files and parameters

It provides mainly two modules:

## Config

A configuration framework based on the [traitlets](https://traitlets.readthedocs.io/) library. It allows for a structured configuration with strict validation of the parameters (enforces type of value and eventual additional validation, raise on unknown or invalid input).
We diverge from the library to give the possibility of a fully nested configuration, compatible with command line arguments, python configuration files (similar to traitlets), but also more conventional configuration files like TOML and YAML.

The configuration structure is easy to setup, using the python class syntax (parameters are class attributes) and the traitlets objects.
After parsing, the values can be obtained by nested attributes (`app.parameters.group.subgroup.parameter`), or retrieved as a more universal nested dictionary.

Beyond input validation, avoiding typos and other possibly silent mistakes, this modules allow to document each parameter (all traitlets objects have a 'help' keyword argument) which I believe is important for scientific projects.
This documentation is used for the command line help, configuration files, and documentation-generating tool Sphinx via an extension.

## Dask-config

This sub-module provides all configuration parameters of [dask clusters](https://docs.dask.org/en/latest/deploying.html), local or deployed on high performance networks.
It can be thought as a showcase, but it also gives "start-up" methods on those configuration objects that start dask clusters and client.

## Dataset

This module aims to ease the creation and management of multiple dataset with different file format, structure, etc. that can depend on various parameters.
Each new dataset is specified by creating a subclass of a dataset object. Relevant attributes or methods are overridden to provide information on this dataset. Each instance of this new subclass corresponds to a set of parameters.

This framework tries to make those dataset objects as universal as reasonably possible.
Some common convenience features are written with the data source and format, or the loading library for instance left unspecified.
Features can be added to the dataset class as necessary via a system of Mixins[^1].

For example, we can make our base dataset class by adding XarrayLoaderMixin and XarrayWriterMixin to load and write data using [xarray](https://xarray.dev/), and FileFinderMixin to manage/find datafiles using the simple syntax of [filefinder](https://filefinder.readthedocs.io/).

``` python
class DatasetDefault(XarrayLoaderMixin, XarrayWriterMixin, FileFinderMixin, DatasetBase):
    OPEN_MFDATASET_KWARGS = dict(parallel=True)
    
    
class SST(DatasetDefault):
    def get_root_directory(self):
        return "/data/SST"

    def get_filename_pattern(self):
        return "%(Y)/SST_%(Y)%(m)%(d).nc"
```

This can allow for a little more advanced functionalities, here for instance we combine the writing mixin with the filefinder one, so that we can automatically split data to different files when writing to disk using the specified filename pattern.

``` python
class DatasetDefault(XarrayLoaderMixin, XarrayWriterComboFileFinderMixin, DatasetBase):
    OPEN_MFDATASET_KWARGS = dict(parallel=True)
    
...

# Say we obtain our SST dataset as a xarray.Dataset,
# we can write our daily data to disk in monthly files
# It would also distribute among any other parameter present in the filename pattern.
# By supplying a Dask client, this is going to be done in parallel.

SST(**maybe_our_parameters).write(
    sst,
    time_freq="M",
    client=client
)
    
```


[^1]: in the works, see branch 'mixins'. Current system uses composition, but it makes for a somewhat confusing interface imho.
