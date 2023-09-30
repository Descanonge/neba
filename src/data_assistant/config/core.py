
from traitlets.config import Configurable
from traitlets.config.loader import KVArgParseConfigLoader, Config, DeferredConfig
from traitlets.utils.text import wrap_paragraphs


class ConfigurablePlus(Configurable):

    def __init_subclass__(cls, /, **kwargs):
        super().__init_subclass__(**kwargs)
        # first setup class descriptors
        cls.setup_class(cls.__dict__)
        # tag all trait not inherited from parent
        for trait in cls.class_own_traits().values():
            # do not tag if metadata already set to False
            if trait.metadata.get('config', True):
                trait.tag(config=True)
        # re-setup class descriptors
        cls.setup_class(cls.__dict__)

    @classmethod
    def generate_config_single_parameter(cls, parameter: str) -> str:
        """Generate config text for a single trait.

        Useful if parameters have been added and the configuration
        file must be changed.
        """
        trait = getattr(cls, parameter)
        # Taken from traitlets.Configurable.class_config_section()
        def c(s):
            s = '\n\n'.join(wrap_paragraphs(s, 78))
            return '## ' + s.replace('\n', '\n#  ')

        lines = []
        default_repr = trait.default_value_repr()

        # cls owns the trait, show full help
        if trait.help:
            lines.append(c(trait.help))
        if 'Enum' in type(trait).__name__:
            # include Enum choices
            lines.append(f'#  Choices: {trait.info}')
        lines.append(f'#  Default: {default_repr}')

        return '\n'.join(lines)


class StrictArgParse(KVArgParseConfigLoader):

    def _handle_unrecognized_alias(self, arg: str):
        self.parser.error(f'Unrecognized alias: {arg}')

    def load_config(self, argv=None, aliases=None, classes=None):
        """Parse command line arguments and return as a Config object.

        Parameters
        ----------
        argv : optional, list
            If given, a list with the structure of sys.argv[1:] to parse
            arguments from. If not given, the instance's self.argv attribute
            (given at construction time) is used.

        Overwritten to raise if any kind of DeferredConfig has been
        parsed (which means the corresponding trait has not been
        defined yet).
        """
        def check_config(cfg, parentkey):
            for key, val in cfg.items():
                fullkey = f'{parentkey}.{key}'
                if isinstance(val, Config):
                    check_config(val, fullkey)
                elif isinstance(val, DeferredConfig):
                    self.parser.error('DeferredConfig not allowed '
                                      f"/ undefined trait '{fullkey}'")

        config = super().load_config(argv=argv, aliases=aliases, classes=classes)
        check_config(config, 'c')
        return config

