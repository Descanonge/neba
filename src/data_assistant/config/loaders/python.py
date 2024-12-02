"""Python configuration file loader."""

from __future__ import annotations

import typing as t
from textwrap import dedent

from traitlets import Enum, TraitType, Type

from ..util import get_trait_typehint, underline, wrap_text
from .core import ConfigValue, FileLoader, SerializerDefault

if t.TYPE_CHECKING:
    from ..scheme import Scheme


class PyConfigContainer:
    """Object that can define attributes recursively on the fly.

    Allows the config file syntax::

        c.group.subgroup.parameter = 3
        c.another_group.parameter = True

    It patches ``__getattribute__`` to allow this. Any unknown attribute is
    automatically created and assigned a new instance of PyConfigContainer. The
    attributes values can be explored (recursively) in the ``__dict__`` attribute.

    This is a very minimalist approach and caution should be applied if this class is to
    be expanded.
    """

    def __getattribute__(self, key: str) -> t.Any:
        try:
            return super().__getattribute__(key)
        except AttributeError:
            obj = PyConfigContainer()
            self.__setattr__(key, obj)
            return obj


class SerializerPython(SerializerDefault):
    def default(self, trait: TraitType, key: str | None = None) -> str:
        try:
            return trait.default_value_repr()
        except Exception:
            return self.value(trait, trait.default(), key=key)

    def value(self, trait: TraitType, value: t.Any, key: str | None = None) -> str:
        if type(trait) is Type:
            return f"{value.__module__}.{value.__qualname__}"
        return repr(value)


class PyLoader(FileLoader):
    """Load config from a python file.

    Follows the syntax of traitlets python config files::

        c.ClassName.parameter = 1

    but now also::

        c.group.subgroup.parameter = True

    Arbitrary schemes and sub-schemes can be specified. The object ``c`` is already
    defined. It is a simple object only meant to allow for this syntax
    (:class:`PyConfigContainer`). Any code will be run, so some logic can be used in the
    config files directly (changing a value depending on OS or hostname for instance).

    Sub-configs are not supported (but could be if necessary).
    """

    serializer = SerializerPython()

    extensions = ["py", "ipy"]

    def load_config(self) -> None:
        """Populate the config attribute from python file.

        Compile the config file, and execute it with the variable ``c`` defined
        as an empty :class:`PyConfigContainer` object.
        """
        read_config = PyConfigContainer()

        # from traitlets.config.loader.PyFileConfigLoader
        namespace = dict(c=read_config, __file__=self.full_filename)
        with open(self.full_filename, "rb") as fp:
            exec(
                compile(source=fp.read(), filename=self.full_filename, mode="exec"),
                namespace,  # globals and locals
                namespace,
            )

        # flatten config
        def recurse(cfg: PyConfigContainer, key: list[str]):
            for k, v in cfg.__dict__.items():
                newkey = key + [k]
                if isinstance(v, PyConfigContainer):
                    recurse(v, newkey)
                else:
                    fullkey = ".".join(newkey)
                    value = ConfigValue(v, fullkey, origin=self.filename)
                    # no parsing, directly to values
                    value.value = value.input
                    self.add(fullkey, value)

        recurse(read_config, [])

    def _to_lines(self, comment: str = "full") -> list[str]:
        """Return lines of configuration file corresponding to the app config tree."""
        lines = self.serialize_scheme(self.app, [], comment=comment)

        lines.append("")
        for key, value in self.config.items():
            lines.append(f"c.{key} = {value.get_value()!r}")

        # newline at the end of file
        lines.append("")

        return lines

    def serialize_scheme(
        self, scheme: Scheme, fullpath: list[str], comment: str = "full"
    ) -> list[str]:
        """Serialize a Scheme and its subschemes recursively.

        If comments are present, trait are separated by double comment lines (##) that
        can be read by editors as magic cells separations.

        For the key = value lines, we make use of :meth:`TraitType.default_value_repr`.
        """
        lines = []
        if comment != "none":
            lines += self.wrap_comment(scheme.emit_description())

        lines.append("")

        for name, trait in sorted(scheme.traits(config=True).items()):
            value = self.serializer.default(trait)

            if comment != "none":
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"## {name} ({typehint}) default: {value}")

            fullkey = ".".join(fullpath + [name])

            uncomment_key = fullkey in self.config
            if uncomment_key:
                value = self.serializer.value(
                    trait, self.config.pop(fullkey).get_value()
                )

            keyval = f"c.{fullkey} = {value}"
            if not uncomment_key:
                keyval = "# " + keyval
            lines.append(keyval)

            if comment != "none" and isinstance(trait, Enum):
                lines.append("# Accepted values: " + repr(trait.values))

            if comment not in ["none", "no-help"] and trait.help:
                lines += self.wrap_comment(trait.help)

            self.wrap_comment(lines)
            if comment != "none":
                lines.append("")

        for name, subscheme in sorted(scheme.trait_values(subscheme=True).items()):
            lines.append("")
            lines.append(f"## {subscheme.__class__.__name__} (.{name}) ##")
            underline(lines, "#")
            lines += self.serialize_scheme(
                subscheme, fullpath + [name], comment=comment
            )

        return lines

    def wrap_comment(self, text: str | list[str]) -> list[str]:
        """Wrap text and return it as commented lines."""
        if not isinstance(text, str):
            text = "\n".join(text)

        text = dedent(text)
        # remove empty trailing lines
        text = text.rstrip(" \n")
        lines = wrap_text(text)
        lines = [f"# {line}" for line in lines]

        lines = [line.rstrip() for line in lines]

        return lines
