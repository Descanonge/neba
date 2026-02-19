"""Toml configuration file loader.

We use :mod:`tomlkit` to parse file.
"""

from __future__ import annotations

from collections.abc import Iterator
from textwrap import dedent
from typing import IO, TYPE_CHECKING, Any, TypeVar

import tomlkit
from tomlkit.container import Container
from tomlkit.items import InlineTable, Item, String, Table, Trivia
from traitlets import Enum

from neba.config.docs import get_trait_typehint, wrap_text
from neba.utils import get_classname

from .core import ConfigValue, DictLikeLoaderMixin, FileLoader

if TYPE_CHECKING:
    from neba.config.section import Section

T = TypeVar("T", bound=Container | Table)


class TomlkitLoader(FileLoader, DictLikeLoaderMixin):
    """Load config from TOML files using tomlkit library.

    The :mod:`tomlkit` library is the default for neba, as it allows precise creation of
    toml files (including comments) which is useful for creating fully documented config
    files.
    """

    def load_config(self) -> Iterator[ConfigValue]:
        """Populate the config attribute from TOML file."""
        with open(self.full_filename) as fp:
            root_table = tomlkit.load(fp)

        return self.resolve_mapping(root_table.unwrap(), origin=self.filename)

    def write(
        self, fp: IO[str], comment: str = "full", comment_default: bool = False
    ) -> None:
        """Return lines of configuration file corresponding to the app config tree."""
        doc = tomlkit.document()

        self.serialize_section(
            doc,
            self.app.__class__,
            [],
            comment=comment,
            comment_default=comment_default,
        )

        tomlkit.dump(doc, fp)

    def serialize_section(
        self,
        t: T,
        section: type[Section],
        fullpath: list[str],
        comment: str = "full",
        comment_default: bool = False,
    ) -> T:
        """Serialize a Section and its subsections recursively.

        We allow to write without the subsections initialized. The config attribute
        will have the instances' values when possible so we don't need to access the
        sections instances here.

        We use the extented capabilities of :mod:`tomlkit`.
        """
        if comment != "none":
            self.wrap_comment(t, section.emit_description())

        traits = section.class_traits(config=True)

        for name, trait in traits.items():
            if comment != "none":
                t.add(tomlkit.nl())
            lines: list[str] = []

            fullkey = ".".join(fullpath + [name])

            default = trait.default()
            value = (
                self.config.pop(fullkey).get_value()
                if fullkey in self.config
                else default
            )

            try:
                t.add(name, self._sanitize_item(value))
            except Exception:
                if value is None:
                    lines.append(f"{name} =")
                else:
                    self.log.warning("Failed to serialize value %s=%s", fullkey, value)
                    lines.append(f"{name} = {value!s}")

            if comment != "none":
                try:
                    default_str = self._sanitize_item(trait.default()).as_string()
                except Exception:
                    default_str = str(trait.default())
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"{fullkey} ({typehint}) default: {default_str}")

                if isinstance(trait, Enum):
                    lines.append("Accepted values: " + repr(trait.values))

            if comment == "full" and trait.help:
                lines += wrap_text(trait.help)

            self.wrap_comment(t, lines)

        for name, subsection in section.class_subsections().items():
            t.add(
                name,
                self.serialize_section(
                    tomlkit.table(),
                    subsection,
                    fullpath + [name],
                    comment=comment,
                    comment_default=comment_default,
                ),
            )

        return t

    def _sanitize_item(self, value: Any) -> Item:
        """Return an Item to use for the line key = value.

        Take care of specific cases when default value is None or a type.
        """
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
            return String.from_raw(get_classname(value))

        return tomlkit.item(value)

    def wrap_comment(self, item: Table | Container, text: str | list[str]) -> None:
        """Wrap text correctly and add it to a toml container as comment lines."""
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = text.splitlines()

        for line in lines:
            item.add(tomlkit.comment(line))
