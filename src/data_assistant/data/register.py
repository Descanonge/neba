"""Registering datasets.

Various possible architectures.

Single file
-----------
All of your DataManager classes are defined in a single file/module.
You can then import any one of them from that module or the store. No special issue.

Separated files, no store
-------------------------
You can separate different DataManagers in different modules for any number of reason.
This is efficient since you import files only as you need them.

But if you want to use the store, it might get more complicated since you may quickly
run in circular imports. Also each module needs te be imported for the store to register
the datasets in them.

Separated files, with store
---------------------------
To avoid these problems, I propose a three part structure:

- A first module, let's call it ``data``. It will define the store variable, and
  eventually some project wide stuff, like a project-default DataManager class so all
  datasets will have common functions.

- Any number of other modules that will define all the datasets needed. They can be
  placed anywhere, in submodules, even outside the project if you're feeling daring.
  They import anything they need from ``data``, and the store object, which they use
  to register.

- Now if we want to use the store, we need to actually import those modules to
  register the datasets inside. Otherwise the store will not know about them.
  One way to do it is to define a third module that will import all the datasets, as
  well as the store, let's call it ``datalist``. It can written like so::

      import sst
      import histogram.dataset
      from data import store
      ...

Once this structure is in place, you can simply import the store from ``datalist``.

Note that this has the disadvantage of importing all module data, which might add some
overhead in some cases for datasets that might not be used.
The store also "hides" the type of the DataManager you get, which can be annoying
when using static type checking.
"""

from collections.abc import Callable, Hashable
from typing import TypeVar, cast

from .data_manager import DataManagerBase

_K = TypeVar("_K", bound=Hashable)
_V = TypeVar("_V", bound=type[DataManagerBase])


class DatasetStore(dict[_K, _V]):
    """Mapping of registered Datasets.

    Maps ID and/or SHORTNAME to a :class:`DataManagerBase` subclass.

    Datasets classes are stored using their unique ID, or SHORTNAME if not
    defined. They can be retrieved using ID or SHORTNAME, as preferred.
    """

    def __init__(self, *args: _V):
        # create empty dict
        super().__init__()

        self.shortnames: list[Hashable] = []
        self.ids: list[Hashable] = []

        for ds in args:
            self.add_dataset(ds)

    def add_dataset(self, ds: _V, name: str | None = None):
        """Register a DataManagerBase subclass."""
        if name is not None:
            key = name
            key_type = "USER"
        elif ds.ID is not None:
            key = ds.ID
            key_type = "ID"
        elif ds.SHORTNAME is not None:
            key = ds.SHORTNAME
            key_type = "SHORTNAME"
        else:
            raise TypeError(f"No ID or SHORTNAME defined in class {ds}")

        if key in self:
            raise KeyError(f"Dataset key {key} ({key_type}) already exists.")

        if ds.SHORTNAME is not None:
            self.shortnames.append(ds.SHORTNAME)
            self.ids.append(key)

        super().__setitem__(cast(_K, key), ds)

    def __getitem__(self, key: _K) -> _V:
        """Return DataManagerBase subclass with this ID or SHORTNAME."""
        if key in self.shortnames:
            if self.shortnames.count(key) > 1:
                raise KeyError(f"More than one Dataset with SHORTNAME: {key}")
            idx = self.shortnames.index(key)
            key = cast(_K, self.ids[idx])
        try:
            return super().__getitem__(key)
        except KeyError as e:
            raise KeyError(
                f"Dataset {key} not found. I have in store: "
                f"{list(self.keys())} and shortnames: {self.shortnames}"
            ) from e

    def register(self, name: str | None = None) -> Callable[[_V], _V]:
        """Register a dataset with a decorator."""

        def decorator(ds: _V) -> _V:
            self.add_dataset(ds, name=name)
            return ds

        return decorator
