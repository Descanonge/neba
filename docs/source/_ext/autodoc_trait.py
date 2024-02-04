from __future__ import annotations

from typing import Any

from sphinx.ext.autodoc import AttributeDocumenter, Documenter, SUPPRESS
from sphinx.application import Sphinx

from traitlets import (
    TraitType,
    Undefined,
    Union,
    Type,
    Instance,
    Container,
    Dict,
    Enum,
)


quit = False


def get_trait_typehint(trait: Any, mode: str = "short") -> str:
    def serialize(obj):
        if isinstance(obj, type):
            cls = obj
        else:
            cls = obj.__class__
        name = cls.__name__
        module = cls.__module__
        out = "~" if mode == "short" else ""
        out += f"{module}.{name}"
        return out

    def recurse(obj):
        return get_trait_typehint(obj, mode)

    if not isinstance(trait, TraitType):
        return serialize(trait)

    typehint = serialize(trait)

    if isinstance(trait, Union):
        interior = " | ".join(recurse(subtrait) for subtrait in trait.trait_types)
        return interior

    if isinstance(trait, Dict):
        key_val = [""]
        has_key = trait._key_trait is not None
        has_val = trait._value_trait is not None

        if has_key:
            key_val[0] = recurse(trait._key_trait)
        if has_val:
            key_val.append(recurse(trait._value_trait))
            if not has_key:
                key_val[0] = "~typing.Any"

        if any(key_val):
            interior = f"[{', '.join(key_val)}]"
        else:
            interior = ""

        return f"{typehint}{interior}"

    if isinstance(trait, Container):
        interior = recurse(trait._trait)
        return f"{typehint}[{interior}]"

    if isinstance(trait, Type | Instance):
        if isinstance(trait.klass, str):
            interior = trait.klass
        else:
            interior = recurse(trait.klass)
        return f"{typehint}[{interior}]"

    return typehint


class TraitDocumenter(AttributeDocumenter):
    priority = AttributeDocumenter.priority + 10

    @classmethod
    def can_document_member(
        cls, member: Any, membername: str, isattr: bool, parent: Any
    ) -> bool:
        if membername == "_subschemes":
            return False

        can_super = super().can_document_member(member, membername, isattr, parent)
        return can_super and isinstance(member, TraitType)

    def get_doc(self) -> list[list[str]]:
        indent = 4 * " "
        lines = []

        # blocked quote for trait metadata
        lines += [r"\ ", ""]

        # default value
        defval = self.object.default_value
        if isinstance(defval, str):
            defval = f'"{defval}"'
        lines += [indent + f"* **Default value:** ``{defval}``"]

        # Enum possible values
        if isinstance(self.object, Enum):
            values = self.object.values
            lines += [indent + f"* **Accepted values:** ``{values}``"]

        # Config path(s)
        paths = self.object.get_metadata("paths")
        if paths is not None:
            if len(paths) == 1:
                lines += [indent + f"* **Path:** ``{paths[0]}``"]
            else:
                lines += [indent + r"* **Paths:**\ "]
                lines += [indent * 2 + f"* ``{path}``" for path in paths]

        # not configurable
        if not self.object.get_metadata("config"):
            lines += [indent + "* **Not configurable**"]

        # read-only
        if self.object.read_only:
            lines += [indent + "* **Read-only**"]

        lines += [""]

        if help := self.object.help:
            lines += help.splitlines()

        return [lines]  # type: ignore

    def import_object(self, raiseerror: bool = False) -> bool:
        ret = super().import_object(raiseerror)

        # self.parent.__annotations__[self.name]
        # import IPython

        # global quit

        # if not quit:
        #     quit = True
        #     IPython.embed()

        return ret

    def add_directive_header(self, sig: str) -> None:
        Documenter.add_directive_header(self, sig)
        sourcename = self.get_sourcename()

        if (
            self.options.annotation is SUPPRESS
            or self.should_suppress_directive_header()
        ):
            return

        if self.options.annotation:
            self.add_line("   :annotation: %s" % self.options.annotation, sourcename)
            return

        if self.config.autodoc_typehints == "none":
            return

        objrepr = get_trait_typehint(self.object, self.config.autodoc_typehints_format)
        alias_key = objrepr.lstrip("~")
        if (alias := self.config.autodoc_type_aliases.get(alias_key, None)) is not None:
            objrepr = alias
        self.add_line("   :type: " + objrepr, sourcename)


def skip_trait_member(app, what, name, obj, skip, options) -> bool:
    """Decide wether to skip trait autodoc.

    By default, autodoc will skip traits without any 'help' attribute. But we can
    add information without docstring (default value, config path, etc.). So we
    implement simple custom logic here.
    """
    if not isinstance(obj, TraitType):
        return skip

    skip = False
    # Check if private (only from name, no docstring analysis)
    if name.startswith("_"):
        if options.get("private_members", None) is None:
            skip = True
        else:
            skip = name not in options["private_members"]

    # unless private, do not skip
    return skip


def setup(app: Sphinx):
    app.setup_extension("sphinx.ext.autodoc")
    app.add_autodocumenter(TraitDocumenter)
    app.connect("autodoc-skip-member", skip_trait_member)

    return dict(
        version="0.1",
        parallel_read_safe=True,
        parallel_write_safe=True,
    )
