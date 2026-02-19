"""JSON configuration file loader."""

import json
from collections.abc import Iterator, Sequence
from typing import IO, Any

from neba.config.types import MultipleConfigKeyError
from neba.utils import get_classname

from .core import ConfigValue, DictLikeLoaderMixin, FileLoader


class JsonEncoderTypes(json.JSONEncoder):
    """Basic JSON encoder.

    Serialize types as strings and lists as sets.
    """

    def default(self, o: Any) -> Any:
        """Serialize object."""
        if isinstance(o, type):
            return get_classname(o)
        if isinstance(o, set):
            return list(o)
        return super().default(o)


def dict_raise_on_duplicate(ordered_pairs: Sequence[tuple[Any, Any]]) -> dict:
    """Raise if there are duplicate keys."""
    d: dict = {}
    for k, v in ordered_pairs:
        if k in d:
            raise MultipleConfigKeyError(k, [v, d[k]])
        d[k] = v
    return d


class JsonLoader(FileLoader, DictLikeLoaderMixin):
    """Loader for JSON files."""

    JSON_DECODER: type[json.JSONDecoder] | None = None
    """Custom json decoder to use."""
    JSON_ENCODER: type[json.JSONEncoder] | None = JsonEncoderTypes
    """Custom json encoder to use."""

    def load_config(self) -> Iterator[ConfigValue]:
        """Populate the config attribute from TOML file.

        We use builtin :mod:`json` to parse file, with eventually a custom decoder
        specified by :attr:`JSON_DECODER`.
        """
        with open(self.full_filename) as fp:
            input = json.load(
                fp, cls=self.JSON_DECODER, object_pairs_hook=dict_raise_on_duplicate
            )

        return self.resolve_mapping(input, origin=self.filename)

    def write(self, fp: IO[str], comment: str = "full") -> None:
        """Serialize configuration."""
        if comment != "none":
            self.app.log.warning("No comments possible in JSON format.")

        data = {k: cv.get_value() for k, cv in self.config.items()}
        data = self.app.nest_dict(data)
        json.dump(data, fp, cls=self.JSON_ENCODER, indent=2)
