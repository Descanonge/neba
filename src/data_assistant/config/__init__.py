
import copy

from traitlets import Bool, Unicode
from traitlets.config import Application, Config, Configurable
from traitlets.config.loader import _is_section_key
from traitlets.config.loader import KVArgParseConfigLoader

from .core import StrictArgParse
from .dask_config import DaskClusterPBS, DaskClusterSLURM
from .parameters import Parameters


class App(Application):
    classes = [Parameters, DaskClusterPBS, DaskClusterSLURM]

    strict_parsing = Bool(
        True, help=('If true, raise errors when encountering unknown '
                    'arguments or configuration keys. Else only prints '
                    'a warning.')
    ).tag(config=True)

    config_file = Unicode(
        'config.py', help='Load this config file'
    ).tag(config=True)

    def setup_defaults(self) -> None:
        """Populate self.config recursively for registered classes."""
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

    def initialize(self, argv=None, ignore_cli: bool = False):
        # Initialize defaults defined in Configurable classes
        self.setup_defaults()

        # First parse CLI (for help for instance, or specify the config files)
        if not ignore_cli:
            self.parse_command_line(argv)

        # Read config files (done last but hasn't priority over CLI)
        if self.config_file:
            self.load_config_file(self.config_file)

    def _create_loader(self, argv, aliases, flags, classes):
        if self.strict_parsing:
            loader = StrictArgParse
        else:
            loader = KVArgParseConfigLoader
        return loader(
            argv, aliases, flags, classes=classes,
            log=self.log, subcommands=self.subcommands
        )

    def _classes_inc_parents(self, classes=None):
        """Iterate through configurable classes, including configurable parents.

        :param classes:
            The list of classes to iterate; if not set, uses :attr:`classes`.

        Children should always be after parents, and each class should only be
        yielded once.

        Overwritten to avoid having the :class:`traitlets.Application` parent
        class documented. I don't think users should change those option
        globally (or at least not in the context of this library).
        """
        for c in super()._classes_inc_parents(classes):
            if c == Application:
                continue
            yield c

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
