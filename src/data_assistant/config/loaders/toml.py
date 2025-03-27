"""Toml configuration file loader."""

from __future__ import annotations

import typing as t
from collections import abc
from textwrap import dedent

import tomlkit
from tomlkit.container import Container
from tomlkit.items import InlineTable, Item, String, Table, Trivia
from traitlets import Enum

from ..section import Section
from ..util import get_trait_typehint, wrap_text
from .core import ConfigValue, DictLikeLoaderMixin, FileLoader

T = t.TypeVar("T", bound=Container | Table)


class TomlkitLoader(FileLoader, DictLikeLoaderMixin):
    """Load config from TOML files using tomlkit library.

    The :mod:`tomlkit` library is the default for data-assistant, as it allows precise
    creation of toml files (including comments) which is useful for creating fully
    documented config files.
    """

    extensions = ["toml"]

    def load_config(self) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from TOML file.

        We use :mod:`tomlkit` to parse file.
        """
        with open(self.full_filename) as fp:
            root_table = tomlkit.load(fp)

        return self.resolve_mapping(root_table.unwrap(), origin=self.filename)

    def _to_lines(self, comment: str = "full") -> list[str]:
        """Return lines of configuration file corresponding to the app config tree."""
        doc = tomlkit.document()

        self.serialize_section(doc, self.app, [], comment=comment)

        for name in sorted(self.app._orphaned_sections):
            section = self.app._orphaned_sections[name]
            table = tomlkit.table()
            self.serialize_section(table, section, [name], comment=comment)
            doc.add(name, table)

        return tomlkit.dumps(doc).splitlines()

    def serialize_section(
        self,
        t: T,
        section: Section | type[Section],
        fullpath: list[str],
        comment: str = "full",
    ) -> T:
        """Serialize a Section and its subsections recursively.

        We use the extented capabilities of :mod:`tomlkit`.
        """
        if comment != "none":
            self.wrap_comment(t, section.emit_description())

        if isinstance(section, type):
            traits = section.class_traits(config=True)
        else:
            traits = section.traits(config=True)

        for name, trait in traits.items():
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

        for name in sorted(section._subsections):
            if isinstance(section, type):
                subsection = section._subsections[name]
            else:
                subsection = getattr(section, name)
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
            return String.from_raw("")

        # tomlkit only creates InlineTables if parent is Array, so we do it manually
        # TODO: inline tables for dict traits could get too longs, maybe we could find a
        # way to accept proper tables (like we do for dict based loaders ?)
        if isinstance(value, dict):
            out = InlineTable(Container(), Trivia(), False)
            for k, v in value.items():
                out[k] = tomlkit.item(v, _parent=out, _sort_keys=False)
            return out

        # Toml does not support sets
        if isinstance(value, set):
            value = list(value)

        # convert types to string
        if isinstance(value, type):
            return String.from_raw(f"{value.__module__}.{value.__name__}")

        return tomlkit.item(value)

    def wrap_comment(self, item: Table | Container, text: str | list[str]):
        """Wrap text correctly and add it to a toml container as comment lines."""
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = text.splitlines()

        for line in lines:
            item.add(tomlkit.comment(line))
