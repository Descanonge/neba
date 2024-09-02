# data-assistant

> Help manage multiple datasets when overwhelmed with many files and parameters

It provides mainly two modules:

## Configuration

The first one for managing the configuration of a project, providing the means to specify a structured, nested configuration in python code using the existing [traitlets](https://traitlets.readthedocs.io/) library. This allows type-checking, value validation and "on-change" callbacks.

The parameters values can be retrieved from configuration files (TOML, YAML, or Python files), or from the command line.

The whole configuration can easily be documented directly inside the specification code, and this is re-used for the command-line help, automatically generated configuration files, and sphinx documentation with a custom autodoc extension.

The submodule [`config.dask_config`](./src/data_assistant/config/dask_config.py) is a show-case of using this for the different parameters necessary when deploying Dask on a local cluster or on distributed machines using [dask-jobqueue](https://jobqueue.dask.org/en/latest/).
It also provides some convenience start-up functions to get setup quickly and easily scale or adapt distributed cluster. It also allows to use the same script for local or distributed clusters.

## Dataset management

The second module aims to ease the creation and management of datasets with different file format, structure, etc. that can all depend on various parameters.

Each new dataset is specified by creating a subclass of a data manager object. Relevant attributes or methods are overridden to provide information on this dataset.
Each *instance* of this new subclass corresponds to a set of parameters that can be used to change aspects of the dataset on the fly: choose only files for a specific year, change the method to open data, etc.

Classes of data managers are made as universal as possible via a system of modules that each cover specific features, and whose implementation can be changed between datasets.
One data manager can deal with multiple source files selected via glob patterns, loaded into pandas, while another could have a remote data-store as input loaded into xarray.

## Documentation

https://biofronts.pages.in2p3.fr/data-assistant

## Requirements

- Python >= 3.11
- traitlets >= 5.13

## Installation

PyPI: someday...🚧 

From source:
``` shell
git clone https://gitlab.in2p3.fr/biofronts/data-assistant
cd data-assistant
pip install -e .
```
or
``` shell
pip install -e https://gitlab.in2p3.fr/biofronts/data-assistant.git#egg=data-assistant
```
