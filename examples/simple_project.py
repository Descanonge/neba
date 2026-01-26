#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

from traitlets import Enum, Float, Int, Unicode

from data_assistant.config.application import ApplicationBase
from data_assistant.config.loaders.json import JsonLoader
from data_assistant.config.loaders.toml import TomlkitLoader
from data_assistant.config.section import Section
from data_assistant.config.util import FixableTrait


class Parameters(Section):
    # Your parameters definition goes here !

    region = Unicode("GS", help="region")
    threshold = Float(5.0, help="threshold for HI")
    kind = Enum(["1thr", "2thr", "2d"], default_value="2thr", help="kind of histogram")
    year = FixableTrait(Int(), 2007)


class App(ApplicationBase):
    aliases = dict(p="parameters")

    file_loaders = [TomlkitLoader, JsonLoader]

    class parameters(Section):
        # Your parameters definition goes here !

        region = Unicode("GS", help="region")
        threshold = Float(5.0, help="threshold for HI")
        kind = Enum(
            ["1thr", "2thr", "2d"], default_value="2thr", help="kind of histogram"
        )
        year = FixableTrait(Int(), 2007)


if __name__ == "__main__":
    app = App()
    # app.add_extra_parameter("--lol", type=int)

    # Values (default or overriden) can be accessed with:
    # print(app.parameters.region)
    print(app.parameters.year)
