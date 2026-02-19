"""Python configuration file loader."""

from collections.abc import Iterator
from textwrap import dedent
from typing import IO, Any

from traitlets import Enum, Instance, TraitType, Type

from neba.config.docs import get_trait_typehint, underline, wrap_text
from neba.config.section import Section
from neba.config.types import ConfigParsingError, MultipleConfigKeyError
from neba.utils import get_classname

from .core import ConfigValue, FileLoader


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

    def __getattribute__(self, key: str) -> Any:
        try:
            return super().__getattribute__(key)
        except AttributeError:
            obj = PyConfigContainer()
            self.__setattr__(key, obj)
            return obj

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self.__dict__:
            raise MultipleConfigKeyError(name, [value, getattr(self, name)])
        super().__setattr__(name, value)

    def as_flat_dict(self) -> dict:
        """Return flat dict of attributes.

        We must use a flat dict, a nested one would not differentiate nested attribute
        and a dictionnary as attribute value.
        """
        out = {}

        def recurse(cfg: PyConfigContainer, key: list[str]) -> None:
            for k, v in cfg.__dict__.items():
                newkey = key + [k]
                if isinstance(v, PyConfigContainer):
                    recurse(v, newkey)
                else:
                    out[".".join(newkey)] = v

        recurse(self, [])
        return out


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

    def load_config(self) -> Iterator[ConfigValue]:
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

    def write(
        self, fp: IO[str], comment: str = "full", comment_default: bool = False
    ) -> None:
        """Return lines of configuration file corresponding to the app config tree."""
        lines = self.serialize_section(
            self.app.__class__, [], comment=comment, comment_default=comment_default
        )

        # newline at the end of file
        lines.append("")

        fp.writelines([f"{line}\n" for line in lines])

    def serialize_section(
        self,
        section: type[Section],
        fullpath: list[str],
        comment: str = "full",
        comment_default: bool = False,
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
            fullkey = ".".join(fullpath + [name])

            default = trait.default()
            is_default = fullkey not in self.config
            value = self.config.pop(fullkey).get_value() if not is_default else default
            try:
                default_str = self.serialize_item(default, trait)
            except Exception:
                default_str = ""

            value_repr = self.serialize_item(value, trait)
            keyval = f"c.{fullkey} = "
            if value_repr is not None:
                keyval += value_repr
            if value_repr is None or (comment_default and is_default):
                keyval = f"# {keyval}"
            lines.append(keyval)

            if comment != "none":
                typehint = get_trait_typehint(trait, "minimal")
                lines.append(f"# {name} ({typehint}) default: {default_str}")
                if isinstance(trait, Enum):
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
                subsection,
                fullpath + [name],
                comment=comment,
                comment_default=comment_default,
            )

        return lines

    def serialize_item(self, value: Any, trait: TraitType) -> str | None:
        """Serialize value using repr."""
        if type(trait) is Type:
            return repr(get_classname(value))
        if type(trait) is Instance:
            return None
        return repr(value)

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
