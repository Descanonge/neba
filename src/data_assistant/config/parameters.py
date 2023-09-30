
from traitlets import Enum, Float, Unicode
from traitlets.config import Configurable

from .utils import generate_config_trait, make_all_configurable

class Parameters(Configurable):

    # Your parameters definition goes here !

    region = Unicode('GS', help='region')
    threshold = Float(5., help='threshold for HI')
    kind = Enum(['1thr', '2thr', '2d'], default_value='2thr',
                help='kind of histogram')

    @classmethod
    def generate_config_single_parameter(cls, parameter: str) -> str:
        """Generate config text for a single trait.

        Useful if parameters have been added and the configuration
        file must be changed.
        """
        trait = getattr(cls, parameter)
        return generate_config_trait(trait)

make_all_configurable(Parameters)
