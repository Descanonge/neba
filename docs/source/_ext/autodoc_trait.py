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
        lines = []

        indent = 4 * " "

        if help := self.object.help:
            lines += help.splitlines()

        lines += [""]
        defval = self.object.default_value
        if defval is not Undefined:
            lines += ["- default: " + str(defval)]
            lines += ["- nom: " + self.object.name]

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


def setup(app: Sphinx):
    app.setup_extension("sphinx.ext.autodoc")
    app.add_autodocumenter(TraitDocumenter)

    return dict(
        version="0.1",
        parallel_read_safe=True,
        parallel_write_safe=True,
    )
