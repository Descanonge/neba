
from traitlets import Enum, Float, Unicode

from .core import ConfigurablePlus

class Parameters(ConfigurablePlus):

    # Your parameters definition goes here !

    region = Unicode('GS', help='region')
    threshold = Float(5., help='threshold for HI')
    kind = Enum(['1thr', '2thr', '2d'], default_value='2thr',
                help='kind of histogram')
