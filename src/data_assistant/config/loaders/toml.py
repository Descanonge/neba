"""Toml configuration file loader."""

from __future__ import annotations

import typing as t
from collections import abc
from textwrap import dedent

import tomlkit
from traitlets import Enum

from ..util import get_trait_typehint, wrap_text
from .core import ConfigValue, FileLoader

if t.TYPE_CHECKING:
    from tomlkit.container import Container as TOMLContainer
    from tomlkit.container import Item, Table

    from .scheme import Section

    T = t.TypeVar("T", bound=TOMLContainer | Table)


class TomlkitLoader(FileLoader):
    """Load config from TOML files using tomlkit library.

    The :mod:`tomlkit` library is the default for data-assistant, as it allows precise
    creation of toml files (including comments) which is useful for creating fully
    documented config files.
    """

    extensions = ["toml"]

    def load_config(self) -> abc.Iterable[ConfigValue]:
        """Populate the config attribute from TOML file.

        We use :mod:`tomlkit` to parse file.
        """
        with open(self.full_filename) as fp:
            root_table = tomlkit.load(fp)

        # flatten tables
        def recurse(table: T, key: list[str]) -> abc.Iterable[ConfigValue]:
            for k, v in table.items():
                newkey = key + [k]
                if isinstance(v, tomlkit.api.Table):
                    yield from recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    yield value

        yield from recurse(root_table, [])

    def _to_lines(self, comment: str = "full") -> list[str]:
        """Return lines of configuration file corresponding to the app config tree."""
        doc = tomlkit.document()

        self.serialize_section(doc, self.app, [], comment=comment)

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

    def serialize_section(
        self, t: T, section: Section, fullpath: list[str], comment: str = "full"
    ) -> T:
        """Serialize a Section and its subsections recursively.

        We use the extented capabilities of :mod:`tomlkit`.
        """
        if comment != "none":
            self.wrap_comment(t, section.emit_description())

        for name, trait in section.traits(config=True).items():
            if comment != "none":
                t.add(tomlkit.nl())
            lines: list[str] = []

            fullkey = ".".join(fullpath + [name])
            update = fullkey in self.config
            if update:
                value = self.config.pop(fullkey).get_value()
                try:
                    t.add(name, self._sanitize_item(value))
                except Exception:
                    update = False
                    self.log.warning("Failed to serialize value %s=%s", fullkey, value)

            # If anything goes wrong we just use str, it may not be valid toml but
            # the default value is in a comment anyway, and the user will deal with it.
            try:
                default = self._sanitize_item(trait.default()).as_string()
            except Exception:
                default = str(trait.default())
            if not update:
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

        for name, subsection in sorted(section.trait_values(subsection=True).items()):
            t.add(
                name,
                self.serialize_section(
                    tomlkit.table(), subsection, fullpath + [name], comment=comment
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
