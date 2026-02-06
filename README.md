# Neba

> Manages parameters and datasets

This package provides:

- configuration framework to retrieve parameters from configuration files and command line arguments,
- a dataset definition framework to help bridge the gap between on-disk files and in-memory objects.

## Configuration

The configuration framework is:
- **strict:** parameters are defined beforehand. Any unknown or invalid parameter will raise errors
- **structured:** parameters can be organized in (nested) sections
- **documented:** docstrings of parameters are re-used in configuration files, command line help, and static documentation via a plugin for Sphinx

The parameters values can be retrieved from configuration files (TOML, YAML, Python files, JSON), and from the command line.

The framework is based on the existing [traitlets](https://traitlets.readthedocs.io/) library. It allows type-checking, arbitrary value validation and "on-change" callbacks.
This package extends it to allow nesting and shifts to a more centralized configuration. The objects containing parameters are significantly extended to ease manipulation, and mimic dictionaries.

Here is a simple example project:
``` python
from neba.config import ApplicationBase, Section
from traitlets import Float, List, Int, Unicode

class App(ApplicationBase):
    # our parameters
    result_dir = Unicode("/data/results", help="Directory containing results") 

    # a nested section called "model"
    class model(Section):
        year = Int(2000)
        coefficients = List(Float(), [0.5, 1.5, 10.0])

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

# coefficients = [0.5, 1.5, 10.0]
# ------------
# model.coefficients (List[Float]) default: [0.5, 1.5, 10.0]

# year = 2000
# ----
# model.year (Int) default: 2000
```

## Dataset management

The second part aims to ease the creation and management of datasets with different file formats, structures, etc. that can all depend on various parameters.

Each new dataset is specified by creating a new subclass.
These classes are made as universal as possible via a system of modules that each cover specific features, and whose implementation can be changed between datasets.
For instance one dataset can deal with multiple source files selected via glob patterns and loaded into Pandas, while another could have a remote data-store as input loaded into Xarray.

An example of a dataset where multiple files are managed with a glob pattern, and fed into Xarray:
``` python
from neba.data import Dataset, GlobSource, ParamsManagerDict
from neba.data.xarray import XarrayLoader

class SST(Dataset):
    # parameters will be held in a simple dict
    Params = ParamsManagerDict
    # loader module uses xarray.open_mfdataset
    Loader = XarrayLoader
    
    # Source module is configured further
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
We used the parameters and loader module as is, but we configured the source module for our needs.
Most modules will use methods like this to take advantage of the parameters contained in the dataset.

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
