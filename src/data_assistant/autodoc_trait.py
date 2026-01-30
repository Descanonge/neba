"""Autodoc extension for automatic documentation of Traits.

Add the extension to your sphinx config (in conf.py):

.. code-block:: py

    extensions = [
        ...,
        "data_assistant.autodoc_trait",
    ]

This adds a new autodoc directive for sections (and applications):

.. code-block:: rst

    .. autosection:: my_module.MySection

It will list traits from all subsections. It will not document any other attribute or
methods.

.. note::

    This uses the legacy autodoc implementation but it does not require you to activate
    it in your configuration.


Options
-------

Other autodoc options apply, but not all may work.

.. rst:directive:option:: inherited-members
    :type: comma separated list

    Works the same as for autodoc. If present, document traits the section inherits from
    parent classes. If a comma separated list, do not document traits inherited from
    those classes.

.. rst:directive:option:: member-order
    :type: alphabetical, bysource or traits-first

    * ``alphabetical``: Sort every trait and section in alphabetical order.
    * ``bysource``: Keep the order from the source files.
    * ``traits-first``: Keep the order from the source files, but put the traits of a
      section before its subsections.

.. rst:directive:option:: only-configurable
    :type:

    Only document configurable traits.
"""

from __future__ import annotations

import sys
import typing as t
from collections import abc
from textwrap import dedent

from docutils import nodes
from sphinx.addnodes import desc_sig_space, desc_signature
from sphinx.domains.python import PyAttribute
from sphinx.ext.autodoc._legacy_class_based._directive_options import bool_option
from sphinx.ext.autodoc._legacy_class_based._documenters import ObjectMember
from sphinx.util.docstrings import prepare_docstring
from sphinx.util.inspect import getdoc
from traitlets import EventHandler, ObserveHandler, ValidateHandler

from data_assistant.config.section import Section
from data_assistant.config.util import (
    FixableTrait,
    get_trait_typehint,
    indent,
    stringify,
    wrap_text,
)

if t.TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.ext.autodoc import ObjectMember

import logging

from sphinx.ext.autodoc import (
    SUPPRESS,
    AttributeDocumenter,
    ClassDocumenter,
    Documenter,
)
from traitlets import Dict, Enum, List, Set, TraitType

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("autodoc_trait")
log.setLevel(logging.INFO)


def member_order_option(arg: t.Any) -> str:
    if arg in {None, True}:
        return "alphabetical"
    elif arg in {"bysource", "traits-first", "alphabetical"}:
        return arg
    else:
        raise ValueError(f"Invalid value for member-order option: {arg}")


class PyAttributeFullkeyTOC(PyAttribute):
    """Attribute that displays the full key in TOC."""

    def _toc_entry_name(self, sig_node: desc_signature) -> str:
        """Display sections leading to trait in TOC."""
        classname, *sections, name = sig_node["_toc_parts"]
        return ".".join([*sections, name])


class PyAttributeSubsection(PyAttributeFullkeyTOC):
    """Attribute that adds 'subsection' before signature."""

    def _toc_entry_name(self, sig_node: desc_signature) -> str:
        """Display sections leading to trait in TOC."""
        classname, *sections, name = sig_node["_toc_parts"]
        return ".".join([*sections, name])

    def get_signature_prefix(self, sig: str) -> list[nodes.Node]:
        prefix = list(super().get_signature_prefix(sig))
        prefix.append(nodes.Text("Section"))
        prefix.append(desc_sig_space())
        return prefix


class TraitDocumenter(AttributeDocumenter):
    """Documenter for Trait objects."""

    objtype = "trait"
    directivetype = "trait"
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
        "observed",
        "validated",
    ]
    """Metadata properties in the order they should appear in doc.

    All properties should return a tuple of the name of the property, and a list of
    lines that document this property. It can return None if the property should be
    skipped. Formatting will be done elsewhere.
    """

    def __init__(
        self,
        *args,
        observers: abc.Sequence[ObjectMember] | None = None,
        validators: abc.Sequence[ObjectMember] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.observers = observers
        self.validators = validators

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

    @property
    def observed(self) -> tuple[str, list[str]] | None:
        """If a trait is observed."""
        if self.observers is None:
            return None

        lines = []
        for obs in self.observers:
            lines += [""]
            lines += [f"- at ``{obs.__name__}``"]
            docstring = getdoc(obs.object.func)
            if docstring:
                summary, *doclines = docstring.splitlines()
                lines[-1] += f": {summary}"
                if doclines:
                    doclines = dedent("\n".join(doclines)).splitlines()
                    lines += indent(doclines, 2)
        lines = indent(lines, 4)
        return ("Observers", lines)

    @property
    def validated(self) -> tuple[str, list[str]] | None:
        """If a trait is custom validated."""
        if self.validators is None:
            return None

        lines = []
        for val in self.validators:
            lines += [""]
            lines += [f"- at ``{val.__name__}``"]
            docstring = getdoc(val.object.func)
            if docstring:
                summary, *doclines = docstring.splitlines()
                lines[-1] += f": {summary}"
                if doclines:
                    doclines = dedent("\n".join(doclines)).splitlines()
                    lines += indent(doclines, 2)
        lines = indent(lines, 4)
        return ("Validators", lines)

    @classmethod
    def can_document_member(
        cls, member: t.Any, membername: str, isattr: bool, parent: t.Any
    ) -> bool:
        """Can this class document this member.

        '_subsections' attribute is not documented.
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
                proplines[1:] = indent(proplines[1:], 2)
                proplines[0] = f"{name}: {proplines[0]}"
                metalines += proplines
            else:
                metalines += [name]

        # indent metadata
        metalines = indent(metalines, 4)
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
            self.add_line(f"   :annotation: {self.options.annotation}", sourcename)
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


class SubsectionDocumenter(AttributeDocumenter):
    """Document for subsections."""

    objtype = "subsection"
    directivetype = "subsection"

    def get_doc(self) -> list[list[str]]:
        docstrings = []
        attrdocstring = getdoc(self.object, self.get_attr)
        if attrdocstring:
            docstrings.append(attrdocstring)
        tab_width = self.directive.state.document.settings.tab_width
        return [prepare_docstring(docstring, tab_width) for docstring in docstrings]


class SectionDocumenter(ClassDocumenter):
    """Documenter for Section objects.

    Currently, custom class documenters are not working that well together with
    autosummary. Autosummary only works with hardcoded object types (the ``objtype``)
    attribute: 'class', 'function', etc. Anything else will be listed as 'data'.
    And we cannot use another directive than autoclass, since this is what autosummary
    will generate. For the moment, we override the class documenter.
    See `<https://github.com/sphinx-doc/sphinx/issues/12021>`.
    """

    objtype = "section"
    directivetype = "class"
    priority = ClassDocumenter.priority + 50
    option_spec = ClassDocumenter.option_spec
    option_spec.update(
        {
            "only-configurables": bool_option,
            "member-order": member_order_option,
        }
    )

    object: type[Section]

    def get_object_members(self, want_all: bool) -> tuple[bool, list[ObjectMember]]:
        """Get object members.

        I use my own thing here to get traits from all subsections.
        I explore the base class to get inherited members and keep the order of members
        of the source file.
        """
        members = {}
        self.observers: dict[str, list[ObjectMember]] = {}
        self.validators: dict[str, list[ObjectMember]] = {}

        def get_members(section: type[Section], fullpath: list[str]):
            # start by inherited members
            inherited_members = self.options.inherited_members
            if inherited_members is None:
                inherited_members = set(b.__name__ for b in section.__mro__[1:])

            for base in reversed(section.__mro__[:-1]):
                # only exclude inherited members for the root section
                if len(fullpath) == 0 and base.__name__ in inherited_members:
                    continue
                for name in base.__dict__:
                    # avoid loops in recursion
                    if name == "_parent":
                        continue
                    # avoid dynamic definitions (already accounted for)
                    if name.startswith("_") and name.endswith("SectionDef"):
                        continue
                    # subsections attributes are not initialized
                    if hasattr(base, "_subsections") and name in base._subsections:
                        obj = base._subsections[name]
                    else:
                        obj = getattr(base, name)

                    fullname = ".".join([*fullpath, name])

                    if isinstance(obj, TraitType):
                        members[("trait", fullname)] = ObjectMember(fullname, obj)

                    elif isinstance(obj, type) and issubclass(obj, Section):
                        # Subsections are automatically subclassed
                        members[("section", fullname)] = ObjectMember(fullname, obj)
                        get_members(obj, fullpath + [name])

                    elif isinstance(obj, ObserveHandler):
                        for trait_name in obj.trait_names:
                            full_trait_name = ".".join([*fullpath, str(trait_name)])
                            self.observers.setdefault(full_trait_name, [])
                            self.observers[full_trait_name].append(
                                ObjectMember(fullname, obj)
                            )
                    elif isinstance(obj, ValidateHandler):
                        for trait_name in obj.trait_names:
                            full_trait_name = ".".join([*fullpath, str(trait_name)])
                            self.validators.setdefault(full_trait_name, [])
                            self.validators[full_trait_name].append(
                                ObjectMember(fullname, obj)
                            )

        get_members(self.object, [])
        return True, self._sort_members(members, self.options.member_order)

    def _sort_members(
        self, members: dict[tuple[str, str], ObjectMember], order: str
    ) -> list[ObjectMember]:
        """Sort members.

        The argument is a dict of tuple: (<trait or section>, <fullname>).
        """
        if order == "alphabetical":
            members_sorted = [members[k] for k in sorted(members, key=lambda k: k[1])]
        elif order == "traits-first":
            sections = sorted([name for kind, name in members if kind == "section"])
            sections.insert(0, "")

            traits_by_section = {}
            # start by longest sections names
            for section in reversed(sections):
                to_add = sorted(
                    [
                        (kind, name)
                        for kind, name in members
                        if kind == "trait" and name.startswith(section)
                    ]
                )
                traits_by_section[section] = [members.pop(k) for k in to_add]

            members_sorted = []
            for section in sections:
                if section:
                    members_sorted.append(members[("section", section)])
                members_sorted += traits_by_section[section]

        else:
            members_sorted = list(members.values())

        return members_sorted

    def document_members(self, want_all: bool = False):
        _, members = self.get_object_members(want_all)
        for mname, member, _ in self.filter_members(members, want_all):
            documenter: Documenter
            if isinstance(member, TraitType):
                documenter = TraitDocumenter(
                    self.directive,
                    mname,
                    self.indent,
                    observers=self.observers.get(mname, None),
                    validators=self.validators.get(mname, None),
                )
            else:
                documenter = SubsectionDocumenter(self.directive, mname, self.indent)

            # Do things manually instead of calling parse_name and import_object
            documenter.object = member
            documenter.modname = ""
            documenter.objpath = [mname]
            documenter.fullname = mname
            documenter.args = ""

            documenter._generate()


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


def setup(app: Sphinx):  # noqa: D103
    app.setup_extension("sphinx.ext.autodoc")

    app.add_config_value(
        "autodoc_trait_only_configurable", True, "env", types=frozenset({bool})
    )

    app.add_directive_to_domain("py", "trait", PyAttributeFullkeyTOC)
    app.add_directive_to_domain("py", "subsection", PyAttributeSubsection)

    app.add_autodocumenter(SectionDocumenter)
    app.add_autodocumenter(TraitDocumenter)
    app.connect("autodoc-skip-member", skip_trait_member)

    return dict(
        version="0.1",
        parallel_read_safe=True,
        parallel_write_safe=True,
    )
