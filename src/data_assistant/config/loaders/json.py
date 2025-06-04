"""JSON configuration file loader."""

import json
import typing as t
from collections import abc

from .core import ConfigValue, DictLikeLoaderMixin, FileLoader


class JsonEncoderTypes(json.JSONEncoder):
    """Json encoder supporting type objects."""

    def default(self, o: t.Any) -> t.Any:
        if isinstance(o, type):
            mod = o.__module__
            name = o.__name__
            return f"{mod}.{name}"
        return super().default(o)


class JsonLoader(FileLoader, DictLikeLoaderMixin):
    """Loader for JSON files.

    :Experimental:
    """

    extensions = ["json"]

    JSON_DECODER: type[json.JSONDecoder] | None = None
    """Custom json decoder to use."""
    JSON_ENCODER: type[json.JSONEncoder] | None = JsonEncoderTypes
    """Custom json encoder to use."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.app.log.warning("%s loader is experimental.", self.__class__)

    def load_config(self) -> abc.Iterator[ConfigValue]:
        """Populate the config attribute from TOML file.

        We use builtin :mod:`json` to parse file, with eventually a custom decoder
        specified by :attr:`JSON_DECODER`.
        """
        with open(self.full_filename) as fp:
            input = json.load(fp, cls=self.JSON_DECODER)

        return self.resolve_mapping(input, origin=self.filename)

    def write(self, fp: t.IO[str], comment: str = "full"):
        """Serialize configuration."""
        if comment != "none":
            self.app.log.warning("No comments possible in JSON format.")

        data = {k: cv.get_value() for k, cv in self.config.items()}
        data = self.app.nest_dict(data)
        json.dump(data, fp, cls=self.JSON_ENCODER, indent=2)
