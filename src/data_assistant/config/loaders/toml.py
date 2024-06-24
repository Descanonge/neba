"""Toml configuration file loader."""

from __future__ import annotations

import typing as t
from textwrap import dedent

import tomlkit
from traitlets import Enum

from ..util import get_trait_typehint, wrap_text
from .core import ConfigValue, FileLoader

if t.TYPE_CHECKING:
    from tomlkit.container import Container as TOMLContainer
    from tomlkit.container import Item, Table

    from .scheme import Scheme

    T = t.TypeVar("T", bound=TOMLContainer | Table)


class TomlkitLoader(FileLoader):
    """Load config from TOML files using tomlkit library.

    The :mod:`tomlkit` library is the default for data-assistant, as it allows precise
    creation of toml files (including comments) which is useful for creating fully
    documented config files.
    """

    extensions = ["toml"]

    def load_config(self) -> None:
        """Populate the config attribute from TOML file.

        We use :mod:`tomlkit` to parse file.
        """
        with open(self.full_filename) as fp:
            root_table = tomlkit.load(fp)

        # flatten tables
        def recurse(table: T, key: list[str]):
            for k, v in table.items():
                newkey = key + [k]
                if isinstance(v, tomlkit.api.Table):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    self.add(fullkey, value)

        recurse(root_table, [])

    def _to_lines(
        self, comment: str = "full", show_existing_keys: bool = False
    ) -> list[str]:
        """Return lines of configuration file corresponding to the app config tree."""
        doc = tomlkit.document()

        self.serialize_scheme(
            doc, self.app, [], comment=comment, show_existing_keys=show_existing_keys
        )

        if show_existing_keys:
            class_keys: dict[str, dict[str, t.Any]] = {}
            for key, value in self.config.items():
                cls, name = key.split(".")
                if cls not in class_keys:
                    class_keys[cls] = {}
                class_keys[cls][name] = value.get_value()

            for cls in class_keys:
                tab = tomlkit.table()
                for key, value in class_keys[cls].items():
                    tab.add(key, self._sanitize_item(value))
                doc.add(cls, tab)

        return tomlkit.dumps(doc).splitlines()

    def serialize_scheme(
        self,
        t: T,
        scheme: Scheme,
        fullpath: list[str],
        comment: str = "full",
        show_existing_keys: bool = False,
    ) -> T:
        """Serialize a Scheme and its subschemes recursively.

        We use the extented capabilities of :mod:`tomlkit`.
        """
        if comment != "none":
            self.wrap_comment(t, scheme.emit_description())

        for name, trait in scheme.traits(config=True).items():
            if comment != "none":
                t.add(tomlkit.nl())
            lines: list[str] = []

            fullkey = ".".join(fullpath + [name])
            key_exist = show_existing_keys and fullkey in self.config
            if key_exist:
                value = self.config.pop(fullkey).get_value()
                t.add(name, self._sanitize_item(value))

            # the actual toml code key = value
            # If anything goes wrong we just use str, it may not be valid toml but
            # the user will deal with it.
            try:
                default = self._sanitize_item(trait.default()).as_string()
            except Exception:
                default = str(trait.default())
            if not key_exist:
                lines.append(f"{name} = {default}")

            if comment == "full":
                # a separator between the key = value and block of help/info
                lines.append("-" * len(name))

            if comment != "none":
                fullkey = ".".join(fullpath + [name])
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"{fullkey} ({typehint}) default: {default}")

                if isinstance(trait, Enum):
                    lines.append("Accepted values: " + repr(trait.values))

            if comment != "no-help" and trait.help:
                lines += wrap_text(trait.help)

            self.wrap_comment(t, lines)

        for name, subscheme in sorted(scheme.trait_values(subscheme=True).items()):
            t.add(
                name,
                self.serialize_scheme(
                    tomlkit.table(),
                    subscheme,
                    fullpath + [name],
                    comment=comment,
                    show_existing_keys=show_existing_keys,
                ),
            )

        return t

    def _sanitize_item(self, value: t.Any) -> Item:
        """Return an Item to use for the line key = value.

        Take care of specific cases when default value is None or a type.
        """
        if value is None:
            return tomlkit.items.String.from_raw("")

        # convert types to string
        if isinstance(value, type):
            return tomlkit.items.String.from_raw(f"{value.__module__}.{value.__name__}")

        return tomlkit.item(value)

    def wrap_comment(self, item: Table | TOMLContainer, text: str | list[str]):
        """Wrap text correctly and add it to a toml container as comment lines."""
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = text.splitlines()

        for line in lines:
            item.add(tomlkit.comment(line))
