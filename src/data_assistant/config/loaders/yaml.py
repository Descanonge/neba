"""Yaml configuration file loader."""

# import pyyaml

from .core import DictLikeLoaderMixin, FileLoader


class YamlLoader(DictLikeLoaderMixin, FileLoader):
    """Loader for Yaml files.

    Not implemented yet.
    """

    extensions = ["yaml", "yml"]

    def load_config(self) -> None:
        raise NotImplementedError()
