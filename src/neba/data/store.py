"""Store and easily access Datasets in a custom mapping."""

import typing as t
from collections import abc

from neba.util import import_item

from .dataset import Dataset

_V = t.TypeVar("_V", bound=type[Dataset])


class DatasetStore(abc.MutableMapping[str, _V]):
    """Mapping of registered Datasets.

    Datasets classes are stored using their unique ID, or SHORTNAME if not
    defined. They can be retrieved using ID or SHORTNAME, as preferred.
    """

    def __init__(self, *args: _V | str):
        self._datasets: dict[str, _V | str] = dict()
        self.shortnames: dict[str, list[str]] = {}
        """Mapping of shortnames to dict keys (the ID by default)."""

        for ds in args:
            self.add(ds)

    def __str__(self) -> str:
        ids_and_short: dict[str, list[str]] = {k: [] for k in self._datasets}
        for s, ids in self.shortnames.items():
            for id in ids:
                if s != id and s not in ids_and_short[id]:
                    ids_and_short[id].append(s)

        key_value = []
        for id, shortnames in ids_and_short.items():
            key = " | ".join([f'"{k}"' for k in [id, *shortnames]])
            ds = self._datasets[id]
            value = f'"{ds}"' if isinstance(ds, str) else ds.__name__
            key_value.append(f"{key} : {value}")

        return f"{{{', '.join(key_value)}}}"

    def __repr__(self) -> str:
        return str(self)

    def add(self, ds: _V | str, name: str | None = None):
        """Register a Dataset subclass.

        Will register it under:
        - `name` if supplied
        - :attr:`.Dataset.ID` if defined
        - :attr:`.Dataset.SHORTNAME` if defined

        If the SHORTNAME attribute is defined, an alias will be stored in
        :attr:`DatasetStore.shortnames`, and the dataset can either be accessed with
        its ID or shortname.

        Parameters
        ----------
        ds
            The dataset class to register, or a fully qualified import string. The
            dataset would then be imported when accessed.
        name
            Use this instead of the ID.
        """
        if name is not None:
            key = name
        elif isinstance(ds, str):
            key = ds.rsplit(".", 1)[-1]
        elif ds.ID is not None:
            key = ds.ID
        elif ds.SHORTNAME is not None:
            key = ds.SHORTNAME
        else:
            raise TypeError(f"No ID or SHORTNAME defined in class {ds}.")

        if key in self._datasets:
            raise KeyError(f"Key {key} already exists.")

        if not isinstance(ds, str) and (shortname := ds.SHORTNAME) is not None:
            if (existing := self._datasets.get(shortname, None)) is not None:
                raise KeyError(
                    f"There is already a dataset ('{existing}') registered with "
                    f"key '{shortname}'."
                )
            self.shortnames.setdefault(shortname, [])
            self.shortnames[shortname].append(key)

        self._datasets[key] = ds

    def _get_id(self, key: str) -> str:
        """Get ID, resolve if key is a shortname."""
        if (ids := self.shortnames.get(key, None)) is not None:
            if len(ids) > 1:
                raise KeyError(f"More than one Dataset with SHORTNAME '{key}' ({ids})")
            key = ids[0]
        return key

    def get_no_import(self, key: str) -> _V | str:
        """Retrieve dataset without importing it if a string."""
        key = self._get_id(key)
        try:
            return self._datasets[key]
        except KeyError as e:
            raise KeyError(
                f"Dataset {key} not found. I have in store: "
                f"{list(self._datasets.keys())} and shortnames: {self.shortnames}"
            ) from e

    def __getitem__(self, key: str) -> _V:
        """Return DataManagerBase subclass with this ID or SHORTNAME.

        Import the dataset if registered as an import string.
        """
        raw = self.get_no_import(key)
        if isinstance(raw, str):
            raw = t.cast(_V, import_item(raw))
            dict.__setitem__(self._datasets, key, raw)
        return raw

    def __setitem__(self, key: str, value: _V | str):
        """Automatically adds shortcuts if value is a Dataset."""
        self.add(value, name=key)

    def __contains__(self, key: t.Any) -> bool:
        """Check registered IDs and Shortnames."""
        return key in self._datasets or key in self.shortnames

    def __len__(self) -> int:
        """Return number of datasets."""
        return len(self._datasets)

    def __iter__(self) -> abc.Iterator[str]:
        """Iterate over datasets."""
        return iter(self._datasets)

    def __delitem__(self, key: str):
        """Delete a dataset."""
        self._datasets.__delitem__(self._get_id(key))
        if key in self.shortnames:
            self.shortnames.pop(key)
        to_remove = []
        for short, ids in self.shortnames.items():
            if key in ids:
                self.shortnames[short].remove(key)
                if not self.shortnames[short]:
                    to_remove.append(short)
        for short in to_remove:
            self.shortnames.pop(short)

    def register(self, name: str | None = None) -> abc.Callable[[_V], _V]:
        """Decorator to register a dataset."""  # noqa: D401

        def decorator(ds: _V) -> _V:
            self.add(ds, name=name)
            return ds

        return decorator
