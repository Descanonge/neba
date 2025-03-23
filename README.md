# data-assistant

> Manages parameters and datasets

This package provides a configuration framework to retrieve parameters from configuration files and command line arguments, and a dataset definition framework to help bridge the gap between on-disk files and in-memory objects.
Both frameworks (configuration and dataset) can be used without the other.

The package provides an optional configuration section for Dask to quickly set things up, and work seamlessly both on a local or distributed cluster.

## Configuration

The configuration framework is:
- **strict:** parameters are defined beforehand. Any unknown or invalid parameter will raise
- **structured:** parameters can be organized in (nested) sections
- **documented:** docstrings of parameters can be transferred to configuration files, command line help, and static documentation via a plugin for Sphinx

The parameters values can be retrieved from configuration files (TOML, YAML, Python files), or from the command line.

The framework is based on the existing [traitlets](https://traitlets.readthedocs.io/) library. It allows type-checking, arbitrary value validation and "on-change" callbacks.
Our package extends it to allow nesting and shifts to a more centralized configuration. The objects containing parameters are significantly extended to ease manipulation, and mimic mappings.

Here is a simple starting project:
``` python
from data_assistant.config import ApplicationBase, Section
from traitlets import Float, List, Int, Unicode

class App(Application):
    # what files to read parameters from
    config_files = ["config.toml"]
    
    # our parameters
    result_dir = Unicode("/data/results", help="some help line or paragraph") 

    # a nested section called "model"
    class model(Section):
        year = Int(2000)
        coefficients = List(Float(), [0.5, 1.5, 10.0])

# Start a global instance and retrieve parameters
app = App.instance()
print(app.model.year)
```


## Dataset management

The second part aims to ease the creation and management of datasets with different file formats, structures, etc. that can all depend on various parameters.

Each new dataset is specified by creating a new subclass.
These classes are made as universal as possible via a system of modules that each cover specific features, and whose implementation can be changed between datasets.
For instance one dataset can deal with multiple source files selected via glob patterns and loaded into Pandas, while another could have a remote data-store as input loaded into Xarray.

An example of a dataset where multiple files are managed with a glob pattern, and fed into Xarray:
``` python
from data_assistant.data import Dataset, GlobSource, ParamsManager
from data_assistant.data.xarray import XarrayMultiFileLoader

class SST(Dataset):
    # parameters module will hold in a dict
    _Params = ParamsManager
    # loader module uses xarray.open_mfdataset
    _Loader = XarrayMultiFileLoader
    
    # Source module is configured further
    class _Source(GlobSource):
        def get_root_directory(self):
            # we use the parameters of the Dataset instance
            root = self.params["data_dir"]
            # this will automatically be joined into a path
            return [self.params[], "SST"]
            
        def get_filename_pattern(self):
            return f"{self.params['year']}/SST_*.nc*"
            
ds = SST(year=2000, data_dir="/data")
sst = ds.get_data()
```
We used the parameters and loader module as is, but we configured the source module for our needs.
Most module will use methods like this to take advantage of the parameters contained in the dataset.

The parameters were simply stored in a dictionary filled at instantiation, but we can also use the configuration framework by registering this class as an "orphan":
``` python
class App(ApplicationBase):
    data_dir = Unicode("/data/")
    year = Int(2000)
    ...

@App.register_orphan()
class SST(Dataset):
    # the parameters are held in a configuration object which
    # is automatically filled from the global app instance
    _Params = ParamsManagerApp

    directory = Unicode("SST")
    
    class _Source(GlobSource)
        def get_root_directory(self):
            return [self.params.data_dir, self.dm.directory]
    ...
```
This causes two things:
- the application will know about our SST class. Configuration is now aware of traits defined therein
- the SST class knows about the application: upon instantiation it will find the global app instance (create it if necessary) and recover its own parameters automatically.
If we pass the arguments `--year=2020 --SST.directory=SST_alt` we can simply use:
``` python
>>> ds = SST()
>>> ds.params.year
2020
>>> ds.directory
"SST_alt"
```

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
