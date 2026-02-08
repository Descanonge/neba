"""Python configuration file loader."""

from __future__ import annotations

import typing as t
from collections import abc
from textwrap import dedent

from traitlets import Enum, Instance, TraitType, Type

from neba.config.section import Section
from neba.config.util import (
    ConfigParsingError,
    MultipleConfigKeyError,
    get_trait_typehint,
    underline,
    wrap_text,
)
from neba.util import get_classname

from .core import ConfigValue, FileLoader, SerializerDefault


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

    def __setattr__(self, name: str, value: t.Any):
        if name in self.__dict__:
            raise MultipleConfigKeyError(name, [value, getattr(self, name)])
        super().__setattr__(name, value)

    def as_flat_dict(self) -> dict:
        """Return flat dict of attributes.

        We must use a flat dict, a nested one would not differentiate nested attribute
        and a dictionnary as attribute value.
        """
        out = {}

        def recurse(cfg: PyConfigContainer, key: list[str]):
            for k, v in cfg.__dict__.items():
                newkey = key + [k]
                if isinstance(v, PyConfigContainer):
                    recurse(v, newkey)
                else:
                    out[".".join(newkey)] = v

        recurse(self, [])
        return out


class SerializerPython(SerializerDefault):
    def default(self, trait: TraitType, key: str | None = None) -> str:
        if trait.default_value is None:
            if isinstance(trait, Type | Instance) and trait.klass is not None:
                return self.value(trait, trait.klass)
            return "None"

        try:
            return trait.default_value_repr()
        except Exception:
            return self.value(trait, trait.default(), key=key)

    def value(self, trait: TraitType, value: t.Any, key: str | None = None) -> str:
        if type(trait) is Type:
            return get_classname(value)
        return repr(value)


class PyLoader(FileLoader):
    """Load config from a python file.

    Follows the syntax of traitlets python config files::

        c.ClassName.parameter = 1

    but now also::

        c.group.subgroup.parameter = True

    Arbitrary sections and sub-sections can be specified. The object ``c`` is already
    defined. It is a simple object only meant to allow for this syntax
    (:class:`PyConfigContainer`). Any code will be run, so some logic can be used in the
    config files directly (changing a value depending on OS or hostname for instance).

    Sub-configs are not supported (but could be if necessary).
    """

    serializer = SerializerPython()

    def load_config(self) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from python file.

        Compile the config file, and execute it with the variable ``c`` defined
        as an empty :class:`PyConfigContainer` object.
        """
        read_config = PyConfigContainer()

        # from traitlets.config.loader.PyFileConfigLoader
        namespace = dict(c=read_config, __file__=self.full_filename)
        with open(self.full_filename, "rb") as fp:
            try:
                exec(
                    compile(source=fp.read(), filename=self.full_filename, mode="exec"),
                    namespace,  # globals and locals
                    namespace,
                )
            except Exception as e:
                raise ConfigParsingError(
                    f"Exception while executing '{self.full_filename}'."
                ) from e

        for key, value in read_config.as_flat_dict().items():
            cv = ConfigValue(value, key, origin=self.filename)
            # no parsing, directly to values
            cv.value = cv.input
            yield cv

    def write(self, fp: t.IO[str], comment: str = "full"):
        """Return lines of configuration file corresponding to the app config tree."""
        lines = self.serialize_section(self.app.__class__, [], comment=comment)

        # newline at the end of file
        lines.append("")

        fp.writelines([f"{line}\n" for line in lines])

    def serialize_section(
        self,
        section: type[Section],
        fullpath: list[str],
        comment: str = "full",
    ) -> list[str]:
        """Serialize a Section and its subsections recursively.

        If comments are present, trait are separated by double comment lines (##) that
        can be read by editors as magic cells separations.

        For the key = value lines, we make use of :meth:`TraitType.default_value_repr`.
        """
        lines = []
        if comment != "none":
            lines += self.wrap_comment(section.emit_description())

        lines.append("")

        traits = section.class_traits(config=True)

        for name, trait in sorted(traits.items()):
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

        for name, subsection in section.class_subsections().items():
            lines.append("")
            lines.append(f"## {subsection.__class__.__name__} (.{name}) ##")
            underline(lines, "#")
            lines += self.serialize_section(
                subsection, fullpath + [name], comment=comment
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
