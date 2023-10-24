
from traitlets.config import Config
from traitlets.config.loader import (
    ConfigFileNotFound, FileConfigLoader, KVArgParseConfigLoader
    )


class StrictArgParse(KVArgParseConfigLoader):
    """Strict config loader for argparse.

    Will raise errors on unrecognized alias or configuration key.
    So ``--Unexisting.param=1`` will raise.
    """

    def _handle_unrecognized_alias(self, arg: str):
        self.parser.error(f'Unrecognized alias: {arg}')


class DictFileConfigLoader(FileConfigLoader):

    def load_config(self):
        """Load the config from a file and return it as a Config object."""
        self.clear()

        try:
            self._find_file()
        except OSError as e:
            raise ConfigFileNotFound(str(e)) from e

        dct = self._read_file_as_dict()
        self.config = self._convert_to_config(dct)
        return self.config

    def _read_file_as_dict(self):
        pass

    def _convert_to_config(self, dct: dict) -> Config:
        return Config(dct)


class TomlFileConfigLoader(DictFileConfigLoader):

    def _read_file_as_dict(self):
        from tomlkit import parse

        with open(self.full_filename) as f:
            input_str = f.read()

        dct = parse(input_str)
        return dct
