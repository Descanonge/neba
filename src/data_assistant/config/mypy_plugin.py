"""Mypy plugin to handle dynamic Section definitions.

Use by adding to the list of plugins in your mypy configuration:
``"data_assistant.config.mypy_plugin"``
"""

from collections import abc

from mypy.nodes import MDEF, ClassDef, PlaceholderNode, SymbolTableNode, TypeInfo
from mypy.plugin import ClassDefContext, Plugin, SemanticAnalyzerPluginInterface
from mypy.plugins.common import add_attribute_to_class
from mypy.types import Instance, TypeVarLikeType

from data_assistant.config.section import _name_to_classdef

SECTION_FULLNAME = "data_assistant.config.section.Section"


class SectionPlugin(Plugin):
    """Plugin for dynamic sections."""

    def get_base_class_hook(
        self, fullname: str
    ) -> abc.Callable[[ClassDefContext], None] | None:
        """Adapt to the dynamic definition of subsections."""
        sym = self.lookup_fully_qualified(fullname)
        if sym and isinstance(sym.node, TypeInfo):
            if any(base.fullname == SECTION_FULLNAME for base in sym.node.mro):
                return self._transform_section

        return None

    def _transform_section(self, ctx: ClassDefContext) -> None:
        transformer = SectionTransformer(ctx)
        transformer.transform()


class SectionTransformer:
    """Reproduce the dynamic definition of Sections.

    Nested class definitions (of Sections) are automatically considered as subsections
    of the same name as the class.

    Notably:

    * modify nested class defs: change their name to "_{name}SectionDef" to hide them
      while conserving them
    * add an attribute corresponding to the subsection (traitlets.Instance[_SectionDef])

    We note in metadata the classes that have been modified so that we do not touch
    them on further passes.
    """

    METADATA_KEY = "SectionTransformerPluginData"

    def __init__(self, ctx: ClassDefContext):
        self.ctx = ctx
        self.cls: ClassDef = ctx.cls
        self.api: SemanticAnalyzerPluginInterface = ctx.api

    @property
    def metadata(self) -> dict:
        """Our metadata spot that will be saved for future passes."""
        meta = self.cls.info.metadata
        if self.METADATA_KEY not in meta:
            meta[self.METADATA_KEY] = {}
        return meta[self.METADATA_KEY]

    def transform(self) -> None:
        """Transform the class.

        Can return early if additional passes are needed.
        """
        subsections_defs = self.collect_subsections_defs()
        new_defs = self.modify_class_defs(subsections_defs)

        self.metadata["moved_class_defs"] = [_name_to_classdef(n) for n in new_defs]

        if not self.register_traitlets_instance():
            if self.api.final_iteration:
                self.api.defer()
            return

        subsections_info = {n: k.info for n, k in new_defs.items()}
        self.assign_attributes(subsections_info)

    def assign_attributes(self, subsections: dict[str, TypeInfo]):
        """Assign new attributes corresponding to subsections.

        We replace by traitlets.Instance[_someSectionDef].
        """
        for name, info in subsections.items():
            typ = Instance(self.traitlets_inst_info, [Instance(info, [])])
            add_attribute_to_class(
                self.api,
                self.cls,
                name=name,
                typ=typ,
                override_allow_incompatible=True,
                overwrite_existing=True,
            )

    @staticmethod
    def change_fullname(node, old: str, new: str, index: int, attr: str = "_fullname"):
        """Change fullname of a node.

        Parameters
        ----------
        node
            Node to modify
        old
            Old name.
        new
            New part of the fullname
        index
            Which part of the fullname to modify, when split between dots `.`.
        attr
            Attribute of the node to modify.
        """
        fullname = getattr(node, attr, None)
        if fullname is None:
            return

        split = fullname.split(".")
        if split[index] == old:
            split[index] = new

        setattr(node, attr, ".".join(split))

    def modify_class_defs(
        self, subsections: dict[str, ClassDef]
    ) -> dict[str, ClassDef]:
        """Modify subsection class defs to hide them.

        It also frees the spot for our new subsection attribute (so we don't need to
        completely remove the old definition either).
        """
        new_defs = {}
        for sub_name, old_def in subsections.items():
            new_def = old_def

            # Change name
            new_name = _name_to_classdef(sub_name)
            index = len(new_def.info.fullname.split(".")) - 1
            new_def.name = new_name

            # Recursively alter the fullname of Nodes
            def change_node(node):
                if isinstance(node, TypeVarLikeType):
                    self.change_fullname(node, sub_name, new_name, index, "fullname")
                    return
                self.change_fullname(node, sub_name, new_name, index, "_fullname")
                if isinstance(node, TypeInfo):
                    change_node(node.defn)
                    for sym in node.names.values():
                        change_node(sym.node)

            # Add definition to table
            def_node = SymbolTableNode(MDEF, new_def.info, plugin_generated=True)
            change_node(def_node.node)
            self.api.add_symbol_table_node(new_name, def_node)

            new_defs[sub_name] = new_def

        return new_defs

    def register_traitlets_instance(self) -> bool:
        """Register the traitlets Type information.

        Return False if mypy failed to resolve the import.
        """
        self.api.add_plugin_dependency("traitlets")
        sym = self.api.lookup_fully_qualified_or_none("traitlets.Instance")
        if (
            sym is None
            or isinstance(sym, PlaceholderNode)
            or not isinstance(sym.node, TypeInfo)
        ):
            return False
        self.traitlets_inst_info: TypeInfo = sym.node

        return True

    def collect_subsections_defs(self) -> dict[str, ClassDef]:
        """Find the subsections to modify.

        Do not return classes defs that have the name of previously modified defs
        (ie either have the name of a previous subsection or a previously hidden class).
        """
        moved_class_defs: list[str] = self.metadata.get("moved_class_defs", [])

        found = {}
        for stmt in self.cls.defs.body:
            if isinstance(stmt, ClassDef):
                name = stmt.info.name.rstrip("_")
                if (
                    _name_to_classdef(name) not in moved_class_defs
                    and isinstance(stmt.info, TypeInfo)
                    and stmt.info.has_base(SECTION_FULLNAME)
                ):
                    found[name] = stmt
        return found


def plugin(version: str) -> type[Plugin]:
    return SectionPlugin
