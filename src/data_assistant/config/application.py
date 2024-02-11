from os import path

from collections.abc import Callable, Generator

from traitlets import Bool, TraitType, Unicode, Instance
from traitlets.config import Application, Configurable
from traitlets.utils.text import wrap_paragraphs

from .loader import ConfigLoader, CLILoader, ConfigKey, FlatConfigType
from .scheme import Scheme


class ApplicationBase(Scheme):
    """Base application class.

    Manages loading config from files and CLI.
    """

    strict_parsing = Bool(
        True,
        help=(
            "If true, raise errors when encountering unknown "
            "arguments or configuration keys. Else only prints "
            "a warning."
        ),
    ).tag(config=True)

    config_file = Unicode("config.py", help="Load this config file.").tag(config=True)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Add subschemes to list of managed classes
        for sub in cls._subschemes.values():
            if sub not in cls.classes:
                cls.classes.append(sub)

    # Lifted from traitlets.config.application.Application
    def _classes_inc_parents(
        self, classes: list[type[Scheme]] | None = None
    ) -> Generator[type[Configurable], None, None]:
        """Iterate through configurable classes, including configurable parents.

        :param classes:
            The list of classes to iterate; if not set, uses subschemes.

        Children should always be after parents, and each class should only be
        yielded once.
        """
        if classes is None:
            classes = list(self._subschemes_recursive())

        seen = set()
        for c in classes:
            # We want to sort parents before children, so we reverse the MRO
            for parent in reversed(c.mro()):
                if issubclass(parent, Configurable) and (parent not in seen):
                    seen.add(parent)
                    yield parent

    def __init__(self, *args, **kwargs) -> None:
        self.cli_config: FlatConfigType = {}
        self.file_config: FlatConfigType = {}
        self.config_norm: FlatConfigType = {}

    @classmethod
    def add_scheme(cls) -> Callable[[type[Configurable]], type[Configurable]]:
        """Decorate a Configurable to make it available to configuration.

        Useful for schemes that are not explicitely specified in the configuration
        structure.
        They will be set as an Instance trait to the application, accessible with the
        name of the class.
        """

        def decorator(conf: type[Configurable]) -> type[Configurable]:
            trait = Instance(klass=conf, args=(), kwargs={}).tag(config=True)
            setattr(cls, conf.__name__, trait)
            return conf

        return decorator

    def _create_cli_loader(
        self, argv: list[str] | None, aliases, flags, classes
    ) -> ConfigLoader:
        return CLILoader(self, log=self.log)

    def add_extra_parameter(
        self,
        name: str,
        trait: TraitType,
        dest: type[Configurable] | str | None = None,
        auto_alias: bool = True,
    ):
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
        dest.setup_class(dest.__dict__)  # type: ignore

        if auto_alias:
            self.aliases[name] = (f"{dest.__name__}.{name}", trait.help)

    def initialize(self, argv=None, ignore_cli: bool = False):
        """Initialize application.

        - Parse command line arguments.
        - Load configuration file.
        - Instanciate schemes

        Parameters
        ----------
        argv:
            If not None override command line arguments.
        ignore_cli:
            If True, do not parse command line arguments. Useful
            for jupyter notebooks for instance.
        """
        # First parse CLI
        # needed for help, or overriding the config files)
        # Sets self.cli_config
        if not ignore_cli:
            self.parse_command_line(argv)

        # Read config files
        # Sets self.config
        if self.config_file:
            self.load_config_file(self.config_file)
        # rewrite this to manage new nested keys

        self.config_raw = self.file_config | self.cli_config

        # self.config_norm = self.normalize_keys(self.config_raw)

        self.instanciate_subschemes()

    # def parse_command_line(self, argv=None) -> None:
    #     assert not isinstance(argv, str)
    #     if argv is None:
    #         argv = self._get_sys_argv(check_argcomplete=bool(self.subcommands))[1:]
    #     self.argv = [cast_unicode(arg) for arg in argv]

    #     # flatten flags&aliases, so cl-args get appropriate priority:
    #     flags, aliases = self.flatten_flags()
    #     classes = list(self._classes_with_config_traits())
    #     loader = self._create_loader(argv, aliases, flags, classes=classes)
    #     try:
    #         self.cli_config = deepcopy(loader.load_config())
    #     except SystemExit:
    #         # traitlets 5: no longer print help output on error
    #         # help output is huge, and comes after the error
    #         raise
    #     self.update_config(self.cli_config)
    #     # store unparsed args in extra_args
    #     self.extra_args = loader.extra_args

    def load_config_files(self) -> None:
        # For each file:
        #   Find appropriate loader
        #   Instanciate and load_config
        #   Output should be flat
        #   Put in self.config_from_files[path]
        # Merge output of different config files into self.files_config
        pass

    def write_config(
        self,
        filename: str | None = None,
        comment: bool = True,
        ask_overwrite: bool = True,
    ):
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
                prompt = "Overwrite with new config? [y/N]"
                try:
                    return input(prompt).lower() or "n"
                except KeyboardInterrupt:
                    print("")  # empty line
                    return "n"

            answer = ask()
            while not answer.startswith(("y", "n")):
                print("Please answer 'yes' or 'no'")
                answer = ask()
            if answer.startswith("n"):
                return

        lines = self.generate_config_file().splitlines()

        # Remove trailing whitespace
        lines = [line.rstrip() for line in lines]

        if not comment:
            for i, line in enumerate(lines):
                if line.startswith("# c."):
                    lines[i] = line.removeprefix("# ")

        with open(filename, "w") as f:
            f.write("\n".join(lines))

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
