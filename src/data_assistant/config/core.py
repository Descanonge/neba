
import copy
from os import path

from traitlets.config import Application, Configurable
from traitlets.config.loader import (
    KVArgParseConfigLoader, Config, DeferredConfig, _is_section_key
)
from traitlets.utils.text import wrap_paragraphs
from traitlets import Bool, TraitType, Unicode


class AutoConfigurable(Configurable):
    """Automatically tag its traits as configurable.

    On class definition (using the ``__init_subclass__`` hook) tag
    all class traits as configurable, unless already tagged as False.
    Just save you from adding ``...).tag(config=True)`` to every trait.

    Also add a class method to generate the config for a single trait.
    """

    def __init_subclass__(cls, /, **kwargs):
        """Subclass init hook."""
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
        file must be changed, but only partially.
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
    """Strict config loader for argparse.

    Will raise errors on unrecognized alias or configuration key.
    So ``--Unexisting.param=1`` will raise.
    """

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


class BaseApp(Application):
    """Base application with some additional features.


    """
    classes = []
    """List of Configurable classes to manage.

    Define yours and put them here.
    """

    add_to_aliases: list[type[Configurable]] = []
    """Automatically add aliases for traits from those Configurable.

    Aliases are the names of the traits. For instance
    ``--Parameters.threshold=5`` can be set directly as ``--threshold=5``.
    """

    strict_parsing = Bool(
        True, help=('If true, raise errors when encountering unknown '
                    'arguments or configuration keys. Else only prints '
                    'a warning.')
    ).tag(config=True)

    config_file = Unicode(
        'config.py', help='Load this config file.'
    ).tag(config=True)

    init_config = Bool(
        False, help='If True, write configuration to file.'
    )

    flags = {
        'init-config': ({'BaseApp': {'init_config': True}}, init_config.help)
    }

    def __init_subclass__(cls, /, **kwargs) -> None:
        """Subclass init hook.

        Any subclass will automatically run this after being defined.

        It adds aliases for all traits of the configurable listed
        in the add_to_aliases class attribute.

        It also re-add flags defined in parent classes (unless
        explicitely overridden).
        """
        super().__init_subclass__(**kwargs)
        for cfg in cls.add_to_aliases:
            for name, trait in cfg.class_traits(config=True).items():
                if name not in cls.aliases:
                    cls.aliases[name] = (f'{cfg.__name__}.{name}', trait.help)

        for n, f in super().flags.items():
            cls.flags.setdefault(n, f)

    def add_extra_parameter(self, name: str, trait: TraitType,
                            dest: type[Configurable] | str | None = None,
                            auto_alias: bool = True):
        """Add a configurable trait to this application configuration.

        Parameters
        ----------
        name:
            Name of the trait.
        trait:
            Trait object to add. It will automatically be tagged as configurable.
            It will be accessible in the config object, under `dest`.
        dest:
            Subclass of :class:`Configurable` that will host the trait (one of
            :attr:`classes` typically). If left to None, it will default to this
            class. If specified as a string, it should correspond to the name
            of a class present in ``App.classes``.
        auto_alias:
            If True (default), it will automatically add an alias so that the
            trait can be set directly with ``--{name}=`` instead of
            ``--{dest}.{name}=``.
        """
        if dest is None:
            dest = self.__class__
        elif isinstance(dest, str):
            idx = [cls.__name__ for cls in self.classes].index(dest)
            dest = self.classes[idx]

        trait.tag(config=True)
        setattr(dest, name, trait)
        dest.setup_class(dest.__dict__)

        if auto_alias:
            self.aliases[name] = (f'{dest.__name__}.{name}', trait.help)

    def initialize(self, argv=None, ignore_cli: bool = False):
        """Initialize application.

        - Populate ``config`` attribute with defaults as defined in the
        various Configurable objects.
        - Parse command line arguments.
        - Load configuration file.

        Parameters
        ----------
        argv:
            If not None override command line arguments.
        ignore_cli:
            If True, do not parse command line arguments. Useful
            for jupyter notebooks for instance.
        """
        # Initialize defaults defined in Configurable classes
        self.setup_defaults()

        # First parse CLI (for help for instance, or specify the config files)
        if not ignore_cli:
            self.parse_command_line(argv)

        # Read config files (done last but hasn't priority over CLI)
        if self.config_file:
            self.load_config_file(self.config_file)

    def start(self):
        """Start application or subcommands."""
        super().start()
        if self.init_config:
            self.write_config()

    def setup_defaults(self) -> None:
        """Populate self.config recursively for registered classes.

        Use the defaults values of traits. Traitlets does not do
        this by default (it implies to walk the nested tree of traits,
        and traitlets allows to keep things lazy).

        We do this to centralize the configuration, instead of
        relying on scattered Configurable instances.
        """
        def populate(cls: type[Configurable],
                     config: Config, key: str):
            subconfig = config.setdefault(key, Config())
            for name, value in cls().trait_values(config=True).items():
                # trait name starts with capital > nested config
                if _is_section_key(name):
                    populate(value, subconfig, name)
                else:
                    subconfig[name] = value

        self.config = Config()
        for cls in self.classes:
            populate(cls, self.config, cls.__name__)
        # save defaults
        self.config_defaults = copy.deepcopy(self.config)

    def write_config(self, filename: str | None = None,
                     ask_overwrite: bool = True):
        """(Over)write a configuration file.

        Parameters
        ----------
        filename:
            Write to this file. If None, the current value of
            :attr:`config_file` is used.
        ask_overwrite:
            If True (default), ask for confirmation if config file
            already exists. Else, overwrite the file without questions.
        """
        if filename is None:
            filename = self.config_file

        filename = path.realpath(filename)

        if path.exists(filename) and ask_overwrite:
            print(f"Config file already exists '{filename}")
            def ask():
                prompt = 'Overwrite with new config? [y/N]'
                try:
                    return input(prompt).lower() or 'n'
                except KeyboardInterrupt:
                    print('')  # empty line
                    return 'n'

            answer = ask()
            while not answer.startswith(('y', 'n')):
                print("Please answer 'yes' or 'no'")
                answer = ask()
            if answer.startswith('n'):
                return

        lines = self.generate_config_file().splitlines()
        # Remove trailing whitespace
        lines = [line.rstrip() for line in lines]

        with open(filename, 'w') as f:
            f.write('\n'.join(lines))

    def _create_loader(self, argv, aliases, flags, classes):
        """Use a strict loader if specified.

        Strict loader is :class:`StrictArgParse`, otherwise the
        default :class:`KVArgParseConfigLoader` is used.
        """
        if self.strict_parsing:
            loader = StrictArgParse
        else:
            loader = KVArgParseConfigLoader
        return loader(
            argv, aliases, flags, classes=classes,
            log=self.log, subcommands=self.subcommands
        )

    def _filter_parent_app(self, classes):
        cls = self.__class__
        def to_keep(c):
            if issubclass(c, Application):
                # Only keep current class, no parents
                return c == cls
            return True
        return [c for c in classes if to_keep(c)]

    def emit_help(self, classes=False):
        """Yield the help-lines for each Configurable class in self.classes.

        If classes=False (the default), only flags and aliases are printed.

        Override to avoid documenting base classes of the application.
        """
        yield from self.emit_description()
        yield from self.emit_subcommands_help()
        yield from self.emit_options_help()

        if classes:
            help_classes = self._classes_with_config_traits()
            help_classes = self._filter_parent_app(help_classes)

            if help_classes:
                yield "Class options"
                yield "============="
                for p in wrap_paragraphs(self.keyvalue_description):
                    yield p
                    yield ""

            for cls in help_classes:
                yield cls.class_get_help()
                yield ""
        yield from self.emit_examples()

        yield from self.emit_help_epilogue(classes)

    def generate_config_file(self, classes=None):
        """Generate default config file from Configurables.

        Override to avoid documenting base classes of the application.
        """
        lines = ["# Configuration file for %s." % self.name]
        lines.append("")
        lines.append("c = get_config()  #" + "noqa")
        lines.append("")
        classes = self.classes if classes is None else classes
        config_classes = list(self._classes_with_config_traits(classes))
        config_classes = self._filter_parent_app(config_classes)
        for cls in config_classes:
            lines.append(cls.class_config_section(config_classes))
        return "\n".join(lines)

    def document_config_options(self):
        """Generate rST format documentation for the config options this application.

        Returns a multiline string.

        Override to avoid documenting base classes of the application.
        """
        classes = self._classes_inc_parents()
        classes = self._filter_parent_app(classes)
        return "\n".join(c.class_config_rst_doc() for c in classes)
