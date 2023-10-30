
import os
from os import path

from traitlets import Bool, TraitType, Unicode
from traitlets.config import Application, Configurable
from traitlets.config.loader import Config
from traitlets.utils.text import wrap_paragraphs

from .scheme import Scheme


class BaseApp(Application, Scheme):
    """Base application with some additional features."""

    auto_aliases: list[type[Configurable]] = []
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

    aliases = {
        'config-file': ('BaseApp.config_file', config_file.help)
    }

    def __init_subclass__(cls, /, **kwargs) -> None:
        """Subclass init hook.

        Any subclass will automatically run this after being defined.

        It adds aliases for all traits of the configurable listed
        in the auto_aliases class attribute.

        It also re-add flags defined in parent classes (unless
        explicitely overridden).
        """
        super().__init_subclass__(**kwargs)

        cls.classes = list(cls._subschemes_recursive())

        for cfg in cls.auto_aliases:
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
            if dest in self._subschemes:
                dest = self._subschemes[dest]
            else:
                idx = [cls.__name__ for cls in self.classes].index(dest)
                dest = self.classes[idx]

        trait.tag(config=True)
        setattr(dest, name, trait)
        dest.setup_class(dest.__dict__)

        if auto_alias:
            self.aliases[name] = (f'{dest.__name__}.{name}', trait.help)

    def initialize(self, argv=None, ignore_cli: bool = False):
        """Initialize application.

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
        # First parse CLI (for help for instance, or specify the config files)
        if not ignore_cli:
            self.parse_command_line(argv)

        # Read config files (done last but hasn't priority over CLI)
        if self.config_file:
            self.load_config_file(self.config_file)

    def validate(self, config: Config | None = None):
        if config is None:
            config = self.config

        for cls in self.classes:
            cls(config=config)

    def get_defaults(self):
        pass

    def write_config(self, filename: str | None = None,
                     comment: bool = True,
                     ask_overwrite: bool = True):
        """(Over)write a configuration file.

        Parameters
        ----------
        filename:
            Write to this file. If None, the current value of
            :attr:`config_file` is used.
        comment:
            If True (default), comment configuration lines.
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

        if not comment:
            for i, line in enumerate(lines):
                if line.startswith('# c.'):
                    lines[i] = line.removeprefix('# ')

        with open(filename, 'w') as f:
            f.write('\n'.join(lines))

    def _filter_parent_app(self, classes):
        for c in classes:
            if issubclass(c, Application) and c != self.__class__:
                continue
            yield c

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
