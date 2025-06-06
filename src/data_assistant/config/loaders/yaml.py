"""Yaml configuration file loader.

This uses :mod:`pyyaml`.
"""

from __future__ import annotations

import logging
from collections import abc
from typing import IO

import yaml

try:
    from yaml import CDumper as Dumper
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Dumper, Loader  # type: ignore[assignment]

from .core import ConfigValue, DictLikeLoaderMixin, FileLoader

log = logging.getLogger(__name__)


class YamlLoader(DictLikeLoaderMixin, FileLoader):
    """Loader for Yaml files."""

    extensions = ["yaml", "yml"]

    def load_config(self) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from YAML file."""
        with open(self.full_filename) as fp:
            data = yaml.load(fp, Loader=Loader)

        return self.resolve_mapping(data, origin=self.filename)

    def write(self, fp: IO, comment: str = "full"):
        """Return lines of configuration file corresponding to the app config tree."""
        if comment != "none":
            log.warning("Comments are not supported for YAML")

        data = {k: cv.get_value() for k, cv in self.config.items()}
        data = self.app.nest_dict(data)
        yaml.dump(data, fp, Dumper=Dumper)
