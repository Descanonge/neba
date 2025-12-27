"""Yaml configuration file loader.

This uses :mod:`ruamel.yaml`.
"""

from __future__ import annotations

import logging
from collections import abc
from typing import IO

from ruamel.yaml import YAML

from .core import ConfigValue, DictLikeLoaderMixin, FileLoader

log = logging.getLogger(__name__)


class YamlLoader(DictLikeLoaderMixin, FileLoader):
    """Loader for Yaml files."""

    def load_config(self) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from YAML file."""
        yaml = YAML(typ="safe")
        with open(self.full_filename) as fp:
            data = yaml.load(fp.read())

        return self.resolve_mapping(data, origin=self.filename)

    def write(self, fp: IO, comment: str = "full"):
        """Return lines of configuration file corresponding to the app config tree."""
        if comment != "none":
            log.warning("Comments are not supported for YAML")

        data = {k: cv.get_value() for k, cv in self.config.items()}
        data = self.app.nest_dict(data)
        yaml = YAML()
        yaml.dump(data, fp)
