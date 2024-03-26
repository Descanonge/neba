"""Autodoc extension for automatic documentation of Traits.

Add a specific Documenter for TraitType and member filter for traits.

It will also replace the default class documenter to handle Schemes. This is only for a
minor thing (filter out unwanted *private* attributes from the documentation), so it
would be recommended to put this extension first, in case other extensions also replace
the default documenter for more useful things...
"""
from __future__ import annotations

import sys
import typing as t

from data_assistant.config.scheme import Scheme
from data_assistant.config.util import (
    FixableTrait,
    get_trait_typehint,
    stringify,
    wrap_text,
)

if t.TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.ext.autodoc import ObjectMember

from sphinx.ext.autodoc import (
    SUPPRESS,
    AttributeDocumenter,
    ClassDocumenter,
    Documenter,
)
from traitlets import Dict, Enum, List, Set, TraitType


class TraitDocumenter(AttributeDocumenter):
    """Documenter for Trait objects."""

    objtype = "trait"
    directivetype = "attribute"
    priority = AttributeDocumenter.priority + 10

    metadata_properties = [
        "default_value",
        "accepted_values",
        "per_key_traits",
        "min_length",
        "max_length",
        "configurable",
        "read_only",
        "fixable",
    ]
    """Metadata properties in the order they should appear in doc.

    All properties should return a tuple of the name of the property, and a list of
    lines that document this property. It can return None if the property should be
    skipped. Formatting will be done elsewhere.
    """

    @property
    def default_value(self) -> tuple[str, list[str]] | None:
        """Default value of trait. Nicely rendered."""
        return ("Default value", [stringify(self.object.default())])

    @property
    def accepted_values(self) -> tuple[str, list[str]] | None:
        """List of accepted values in an Enum."""
        if isinstance(self.object, Enum) and (values := self.object.values) is not None:
            return ("Accepted values", [", ".join([stringify(v) for v in values])])
        return None

    @property
    def per_key_traits(self) -> tuple[str, list[str]] | None:
        """List of per key traits in a Dict."""
        if isinstance(self.object, Dict):
            if self.object._per_key_traits is not None:
                lines = [""]
                for key, trait in self.object._per_key_traits.items():
                    lines += [f"   * *{key}*: {(stringify(type(trait)))}"]
                return ("Per key traits", lines)
        return None

    @property
    def min_length(self) -> tuple[str, list[str]] | None:
        """Minimum length of a list/set, if greater than 0 (default)."""
        if isinstance(self.object, List | Set):
            if self.object._minlen > 0:
                return ("Minimum length", [stringify(self.object._minlen)])
            pass
        return None

    @property
    def max_length(self) -> tuple[str, list[str]] | None:
        """Maximum length of a list/set, if less than sys.maxsize (default)."""
        if isinstance(self.object, List | Set):
            if self.object._maxlen < sys.maxsize:
                return ("Maximum length", [stringify(self.object._maxlen)])
            pass
        return None

    @property
    def configurable(self) -> tuple[str, list[str]] | None:
        """If trait is configurable."""
        if not self.object.get_metadata("config"):
            return ("Not configurable", [])
        return None

    @property
    def read_only(self) -> tuple[str, list[str]] | None:
        """If trait is read-only."""
        if self.object.read_only:
            return ("Read-only", [])
        return None

    @property
    def fixable(self) -> tuple[str, list[str]] | None:
        """If trait correspond to a fixable parameter.

        ie a parameter defined in a filename pattern from :mod:`filefinder`.
        """
        if isinstance(self.object, FixableTrait):
            return ("Filename pattern parameter ('fixable')", [])
        return None

    @classmethod
    def can_document_member(
        cls, member: t.Any, membername: str, isattr: bool, parent: t.Any
    ) -> bool:
        """Can this class document this member.

        '_subschemes' attribute is not documented.
        """
        can_super = super().can_document_member(member, membername, isattr, parent)
        return can_super and isinstance(member, TraitType)

    def get_doc(self) -> list[list[str]]:
        """Return documentation paragraphs.

        This overwrite gets the documentation from the help attribute of traits, and
        add metadata/information about the trait (default value, etc.).

        The metadata is dictated by the properties listed in
        :attr:`metadata_properties`.
        """
        indent = 4 * " "
        lines = []

        # we need at least one not empty line to have a block quote
        lines += [r"\ ", ""]

        metalines = []
        for prop in self.metadata_properties:
            res = getattr(self, prop)
            if res is None:
                continue

            name, proplines = res
            name = f"* **{name}**"
            if proplines:
                proplines[0] = f"{name}: {proplines[0]}"
                metalines += proplines
            else:
                metalines += [name]

        # indent metadata
        metalines = [indent + line for line in metalines]
        lines += metalines
        # end of blocked quote
        lines += [""]

        if help := self.object.help:
            lines += wrap_text(help)

        return [lines]  # type: ignore

    def add_directive_header(self, sig: str) -> None:
        """Add directives to the object header.

        Overwrite completely implementation from AttributeDocumenter to obtain the
        typehint from the trait itself, and remove the value directive (default
        value is documented elsewhere).
        """
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

        objrepr = get_trait_typehint(
            self.object,
            mode=self.config.autodoc_typehints_format,
            aliases=self.config.autodoc_type_aliases,
        )
        alias_key = objrepr.lstrip("~")
        if (alias := self.config.autodoc_type_aliases.get(alias_key, None)) is not None:
            objrepr = alias
        self.add_line("   :type: " + objrepr, sourcename)


def skip_trait_member(app, what, name, obj, skip, options) -> bool | None:
    """Decide whether to skip trait autodoc.

    By default, autodoc will skip traits without any 'help' attribute. But we can
    add information without docstring (default value, config path, etc.). So we
    implement simple custom logic here.
    """
    if not isinstance(obj, TraitType):
        return None

    skip = False
    # Check if private (only from name, no docstring analysis)
    if name.startswith("_"):
        if options.get("private_members", None) is None:
            skip = True
        else:
            skip = name not in options["private_members"]

    # unless private, do not skip
    return skip


class SchemeDocumenter(ClassDocumenter):
    """Documenter for Scheme objects.

    Used to filter ``_subschemes`` attributes away, as well as some undocumented members
    that pop up from HasTraits. The skip event does not give information on the parent
    object to do that so we use a custom documenter.

    Currently, custom class documenters are not working that well together with
    autosummary. Autosummary only works with hardcoded object types (the ``objtype``)
    attribute: 'class', 'function', etc. Anything else will be listed as 'data'.
    And we cannot use another directive than autoclass, since this is what autosummary
    will generate. For the moment, we override the class documenter.
    See `<https://github.com/sphinx-doc/sphinx/issues/12021>`.
    """

    def filter_members(
        self, members: list[ObjectMember], want_all: bool
    ) -> list[tuple[str, t.Any, bool]]:
        """Filter the given member list.

        If self is a subclass of :class:`~.config.scheme.Scheme`, but not Scheme itself
        (for our own package documentation), filter out the ``_subschemes`` attribute.
        """
        filtered = super().filter_members(members, want_all)

        to_remove = [
            "_all_trait_default_generators",
            "_descriptors",
            "_instance_inits",
            "_static_immutable_initial_values",
            "_trait_default_generators",
            "_traits",
        ]

        if issubclass(self.object, Scheme):
            if self.object is not Scheme:
                to_remove.append("_subschemes")
            filtered = [
                (name, member, isattr)
                for name, member, isattr in filtered
                if name not in to_remove
            ]
        return filtered


def setup(app: Sphinx):  # noqa: D103
    app.setup_extension("sphinx.ext.autodoc")
    app.add_autodocumenter(TraitDocumenter)
    app.add_autodocumenter(SchemeDocumenter, False)
    app.connect("autodoc-skip-member", skip_trait_member)

    return dict(
        version="0.1",
        parallel_read_safe=True,
        parallel_write_safe=True,
    )
