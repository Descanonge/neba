# Neba

> Manage parameters and datasets

<div align="left">

[![PyPI](https://img.shields.io/pypi/v/neba)](https://pypi.org/project/neba)
[![GitHub release](https://img.shields.io/github/v/release/Descanonge/neba)](https://github.com/Descanonge/neba/releases)
[![test status](https://github.com/Descanonge/neba/actions/workflows/ci.yml/badge.svg)](https://github.com/Descanonge/neba/actions)
[![codecov](https://codecov.io/gh/Descanonge/neba/graph/badge.svg?token=PF281O06Y5)](https://codecov.io/gh/Descanonge/neba)
[![Documentation Status](https://readthedocs.org/projects/neba/badge/?version=latest)](https://neba.readthedocs.io/en/latest/?badge=latest)

</div>

- Obtain your parameters from configuration files or command line arguments. Validate them against a structured specification that is easy to write, expandable, and which allows to document every parameter.
- Declare datasets in a flexible way to manage multiple source files and to read and write data easily using different libraries.

## Configuration

The configuration framework is:
- **strict:** parameters are defined beforehand. Any unknown or invalid parameter will raise errors
- **structured:** parameters can be organized in (nested) sections
- **documented:** docstrings of parameters are re-used in configuration files, command line help, and static documentation via a plugin for Sphinx

The parameters values can be retrieved from configuration files (TOML, YAML, Python files, JSON), and from the command line.

The framework is based on the existing [traitlets](https://traitlets.readthedocs.io/) library. It allows type-checking, arbitrary value validation and "on-change" callbacks.
This package extends it to allow nesting. The objects containing parameters are significantly extended to ease manipulation.

Here is a simple example project:
``` python
from neba.config import ApplicationBase, Section
from traitlets import Enum, Float, List, Unicode

class App(ApplicationBase):
    """The application will retrieve and store parameters."""

    result_dir = Unicode("/data/results", help="Directory containing results") 

    class model(Section):
        """A nested section."""
        coefficients = List(Float(), [0.5, 1.5, 10.0], help="Some coefficients for computation.")
        style = Enum(["serial", "parallel"], "serial", help="Only some values are accepted.")

app = App()
print(app.model.year)
```

Parameters from the example above could be retrieved from the command line with `--result_dir "./some_dir" --model.coefficients 0 2.5 10`. The application can generate a configuration file, for instance in TOML:
``` toml
# result_dir = "/data/results"
# ----------
# result_dir (Unicode) default: "/data/results"
# Directory containing results

[model]
# A nested section.

# coefficients = [0.5, 1.5, 10.0]
# ------------
# model.coefficients (List[Float]) default: [0.5, 1.5, 10.0]
# Some coefficients for computation

# style = "serial"
# -----
# model.style (Enum) default: "serial"
# Accepted values: ['serial', 'parallel']
# Only some values are accepted
```

## Dataset management

The second part aims to ease the creation and management of datasets with different file formats, structures, etc.
Each new dataset is specified by creating a new subclass. It contains
interchangeable *modules* that each cover some functionalities. One dataset can
deal with multiple source files selected via glob patterns, loaded into pandas,
while another could have a remote data-store as input loaded into xarray.

Here is an example of a dataset where multiple files are found with a glob pattern, and fed into Xarray:
``` python
from neba.data import Dataset, GlobSource, ParamsManagerDict
from neba.data.xarray import XarrayLoader

class SST(Dataset):
    # manage parameters with a simple dict
    ParamsManager = ParamsManagerDict

    # load data using xarray
    Loader = XarrayLoader
    Loader.OPEN_MFDATASET_KWARGS = dict(parallel=True)
    
    # find files on disk using glob
    class Source(GlobSource):
        def get_root_directory(self):
            # we use the parameters of the Dataset instance
            root = self.params["data_dir"]
            # this will automatically be joined into a path
            return [root, "SST"]
            
        def get_filename_pattern(self):
            return f"{self.params['year']}/SST_*.nc*"
            
ds = SST(year=2000, data_dir="/data")
sst = ds.get_data()
```
We used the parameters and loader modules as is, but we configured the source module for our needs.

## Documentation

https://neba.readthedocs.io/en/latest/

## Requirements

- Python >= 3.11
- [traitlets](https://pypi.org/project/traitlets/) >= 5.13
- [Levenshtein](https://pypi.org/project/Levenshtein/) >= 0.27

## Installation

From PyPI:
``` shell
pip install neba
```

From source:
``` shell
git clone https://github.com/Descanonge/neba
cd neba
pip install -e .
```
or
``` shell
pip install -e https://github.com/Descanonge/neba.git#egg=neba
```
