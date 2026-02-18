"""Yaml configuration file loader.

This uses :mod:`ruamel.yaml`.
"""

from __future__ import annotations

import logging
import typing as t
from collections import abc
from typing import IO

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, CommentedSet
from traitlets import Instance, List, Set, TraitType, Tuple

from neba.config.docs import get_trait_typehint, wrap_text
from neba.utils import get_classname

from .core import ConfigValue, DictLikeLoaderMixin, FileLoader

if t.TYPE_CHECKING:
    from neba.config.section import Section

log = logging.getLogger(__name__)


class NoOp:
    """Do not insert this value."""


class YamlLoader(DictLikeLoaderMixin, FileLoader):
    """Loader for Yaml files."""

    yaml: YAML

    def setup_yaml(self) -> None:
        """Set up main YAML instance.

        You can customize the yaml parsing and serializing here.
        """
        self.yaml = YAML()
        self.yaml.Representer.ignore_aliases = lambda r, data: True
        self.yaml.default_flow_style = False
        self.yaml.compact(seq_seq=True, seq_map=True)

    def load_config(self) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from YAML file."""
        self.setup_yaml()

        with open(self.full_filename) as fp:
            data = self.yaml.load(fp.read())

        # empty file
        if data is None:
            data = {}

        for cv in self.resolve_mapping(data, origin=self.filename):
            if isinstance(cv.value, CommentedSet):
                cv.value = set(cv.value.odict.keys())
            yield cv

    def serialize_section(
        self,
        data: CommentedMap,
        section: type[Section],
        fullpath: list[str],
        comment: str = "full",
    ) -> None:
        """Populate `data` mapping."""
        traits = section.class_traits(config=True)
        for name, trait in traits.items():
            fullkey = ".".join(fullpath + [name])
            update = fullkey in self.config

            value = self.config.pop(fullkey).get_value() if update else trait.default()
            to_insert = self._sanitize_item(value, trait)
            if to_insert is not NoOp:
                data[name] = self._sanitize_item(value, trait)
                last_key = name

            if trait.default() is None:
                default = "None"
            else:
                default = str(trait.default())

            eol_comment = []
            if comment != "none":
                eol_comment.append(f"({get_trait_typehint(trait, 'minimal')})")
            eol_comment.append(f"default: {default}")
            data.yaml_add_eol_comment(" ".join(eol_comment), name)

            if comment == "full":
                for line in wrap_text(trait.help):
                    data.yaml_set_comment_before_after_key(last_key, after=line)

        for name, subsection in section.class_subsections().items():
            data[name] = CommentedMap()

            if comment == "full":
                for line in subsection.emit_description():
                    data.yaml_set_comment_before_after_key(name, after=line)

            self.serialize_section(
                data[name], subsection, fullpath + [name], comment=comment
            )

    def _sanitize_item(self, value: t.Any, trait: TraitType) -> t.Any:
        if isinstance(value, type):
            return get_classname(value)

        if isinstance(trait, Instance):
            # check if there is a representer registered
            # I am not sure this is the proper way to do that
            representer = self.yaml.representer
            if (
                type(value) not in representer.yaml_representers
                and type(value) not in representer.yaml_multi_representers
            ):
                return NoOp

        # Sets are not very ergonomic in yaml, we use a sequence instead.
        # We convert it back when loading.
        if isinstance(trait, List | Tuple | Set):
            value = CommentedSeq(value)
            value.fa.set_flow_style()
            return value

        return value

    def write(self, fp: IO, comment: str = "full") -> None:
        """Return lines of configuration file corresponding to the app config tree."""
        self.setup_yaml()
        data = CommentedMap()

        if comment == "full":
            if descr := "\n".join(self.app.emit_description()):
                data.yaml_set_start_comment(descr)

        self.serialize_section(data, self.app.__class__, [], comment=comment)
        self.yaml.dump(data, fp)
