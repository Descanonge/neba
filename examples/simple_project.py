from data_assistant.config.application import ApplicationBase
from data_assistant.config.dask_config import DaskConfig
from data_assistant.config.scheme import Scheme
from traitlets import Enum, Float, Unicode

# DaskConfig.set_selected_clusters(['local', 'slurm'])


class Parameters(Scheme):
    # Your parameters definition goes here !

    region = Unicode("GS", help="region")
    threshold = Float(5.0, help="threshold for HI")
    kind = Enum(["1thr", "2thr", "2d"], default_value="2thr", help="kind of histogram")


class App(ApplicationBase):
    parameters = Parameters
    dask = DaskConfig
    auto_aliases = [Parameters]


if __name__ == "__main__":
    app = App()

    # Values (default or overriden) can be accessed with:
    print(app.parameters.region)
