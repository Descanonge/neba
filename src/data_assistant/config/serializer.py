
from traitlets.config.core import ConfigDict
from traitlets.config.loader import FileConfigLoader

class TomlSerializer(FileConfigLoader):
    def __init__(self, *args, **kwargs):
        import tomlkit
        self.toml = tomlkit

    def serialize_config(self, config: BaseApp):
