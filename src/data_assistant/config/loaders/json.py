"""JSON configuration file loader."""

import json
import typing as t

from .core import DictLikeLoaderMixin, FileLoader


class JsonEncoderTypes(json.JSONEncoder):
    """Json encoder supporting type objects."""

    def default(self, o: t.Any) -> t.Any:
        if isinstance(o, type):
            mod = o.__module__
            name = o.__name__
            return f"{mod}.{name}"
        return super().default(o)


class JsonLoader(DictLikeLoaderMixin, FileLoader):
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

    def load_config(self) -> None:
        """Populate the config attribute from TOML file.

        We use builtin :mod:`json` to parse file, with eventually a custom decoder
        specified by :attr:`JSON_DECODER`.
        """
        with open(self.full_filename) as fp:
            input = json.load(fp, cls=self.JSON_DECODER)

        self.resolve_mapping(input, origin=self.filename)

    def _to_lines(
        self, comment: str = "full", show_existing_keys: bool = False
    ) -> list[str]:
        """Serialize configuration."""
        if comment != "none":
            self.app.log.warning("No comments possible in JSON format.")

        output = self.app.values_recursive()
        # TODO Merge with self.config
        # TODO Options: maybe only show values differing from default?
        dump = json.dumps(output, cls=self.JSON_ENCODER, indent=2)

        return dump.splitlines()
