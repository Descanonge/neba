
from traitlets import Enum, Float, Unicode

from data_assistant.config import BaseApp
from data_assistant.config import AutoConfigurable
from data_assistant.config.dask_config import DaskApp


class Parameters(AutoConfigurable):
    # Your parameters definition goes here !

    region = Unicode('GS', help='region')
    threshold = Float(5., help='threshold for HI')
    kind = Enum(['1thr', '2thr', '2d'], default_value='2thr',
                help='kind of histogram')


class App(BaseApp, DaskApp):
    classes = [Parameters]
    auto_aliases = [Parameters]


if __name__ == '__main__':
    app = App()

    app.add_extra_parameter('unique-param',
                            Unicode('for this script alone'),
                            dest='Parameters')

    # Initialize: this retrieves the configuration values from
    # config file or command line arguments.
    app.initialize()

    # Eventually, execute some actions if prompted like printing
    # the configuration or overwritting the config file.
    app.start()

    # The configuration can be access in the form of a nested
    # dictionnary (traitlets.config.ConfigDict)
    c = app.config
