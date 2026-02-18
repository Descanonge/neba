"""Store and easily access interfaces in a custom mapping."""

import typing as t
from collections import abc

from neba.utils import import_item

from .interface import DataInterface

_V = t.TypeVar("_V", bound=type[DataInterface])


class DataInterfaceStore(abc.MutableMapping[str, _V]):
    """Mapping of registered interfaces.

    Interface classes are stored using their unique ID, or SHORTNAME if not defined.
    They can be retrieved using ID or SHORTNAME, as preferred.
    """

    def __init__(self, *args: _V | str):
        self._interfaces: dict[str, _V | str] = dict()
        self.shortnames: dict[str, list[str]] = {}
        """Mapping of shortnames to dict keys (the ID by default)."""

        for di in args:
            self.add(di)

    def __str__(self) -> str:
        ids_and_short: dict[str, list[str]] = {k: [] for k in self._interfaces}
        for s, ids in self.shortnames.items():
            for id in ids:
                if s != id and s not in ids_and_short[id]:
                    ids_and_short[id].append(s)

        key_value = []
        for id, shortnames in ids_and_short.items():
            key = " | ".join([f'"{k}"' for k in [id, *shortnames]])
            di = self._interfaces[id]
            value = f'"{di}"' if isinstance(di, str) else di.__name__
            key_value.append(f"{key} : {value}")

        return f"{{{', '.join(key_value)}}}"

    def __repr__(self) -> str:
        return str(self)

    def add(self, di: _V | str, name: str | None = None):
        """Register an interface subclass.

        Will register it under:
        - `name` if supplied
        - :attr:`.DataInterface.ID` if defined
        - :attr:`.DataInterface.SHORTNAME` if defined

        If the SHORTNAME attribute is defined, an alias will be stored in
        :attr:`InterfaceStore.shortnames`, and the interface can either be accessed with
        its ID or shortname.

        Parameters
        ----------
        di
            The interface class to register, or a fully qualified import string. The
            interface would then be imported when accessed.
        name
            Use this instead of the ID.
        """
        if name is not None:
            key = name
        elif isinstance(di, str):
            key = di.rsplit(".", 1)[-1]
        elif di.ID is not None:
            key = di.ID
        elif di.SHORTNAME is not None:
            key = di.SHORTNAME
        else:
            raise TypeError(f"No ID or SHORTNAME defined in class {di}.")

        if key in self._interfaces:
            raise KeyError(f"Key {key} already exists.")

        if not isinstance(di, str) and (shortname := di.SHORTNAME) is not None:
            if (existing := self._interfaces.get(shortname, None)) is not None:
                raise KeyError(
                    f"There is already an interface ('{existing}') registered with "
                    f"key '{shortname}'."
                )
            self.shortnames.setdefault(shortname, [])
            self.shortnames[shortname].append(key)

        self._interfaces[key] = di

    def _get_id(self, key: str) -> str:
        """Get ID, resolve if key is a shortname."""
        if (ids := self.shortnames.get(key, None)) is not None:
            if len(ids) > 1:
                raise KeyError(
                    f"More than one interface with SHORTNAME '{key}' ({ids})"
                )
            key = ids[0]
        return key

    def get_no_import(self, key: str) -> _V | str:
        """Retrieve interface without importing it if a string."""
        key = self._get_id(key)
        try:
            return self._interfaces[key]
        except KeyError as e:
            raise KeyError(
                f"Interface {key} not found. I have in store: "
                f"{list(self._interfaces.keys())} and shortnames: {self.shortnames}"
            ) from e

    def __getitem__(self, key: str) -> _V:
        """Return interface subclass with this ID or SHORTNAME.

        Import the interface if registered as an import string.
        """
        raw = self.get_no_import(key)
        if isinstance(raw, str):
            raw = t.cast(_V, import_item(raw))
            dict.__setitem__(self._interfaces, key, raw)
        return raw

    def __setitem__(self, key: str, value: _V | str):
        """Automatically adds shortcuts if value is an interface."""
        self.add(value, name=key)

    def __contains__(self, key: t.Any) -> bool:
        """Check registered IDs and Shortnames."""
        return key in self._interfaces or key in self.shortnames

    def __len__(self) -> int:
        """Return number of interfaces."""
        return len(self._interfaces)

    def __iter__(self) -> abc.Iterator[str]:
        """Iterate over interfaces."""
        return iter(self._interfaces)

    def __delitem__(self, key: str):
        """Delete an interface."""
        self._interfaces.__delitem__(self._get_id(key))
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
        """Decorator to register an interface."""  # noqa: D401

        def decorator(di: _V) -> _V:
            self.add(di, name=name)
            return di

        return decorator
