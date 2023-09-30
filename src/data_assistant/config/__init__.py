
from traitlets import Unicode
from traitlets.config import Application, Config

from .core import StrictArgParse
from .dask_config import DaskClusterPBS, DaskClusterSLURM
from .parameters import Parameters

class App(Application):
    classes = [Parameters, DaskClusterPBS, DaskClusterSLURM]

    config_file = Unicode(
        'config.py', help='Load this config file'
    ).tag(config=True)

    def initialize(self, argv=None):
        # Setup defaults
        # TODO Nested config ?
        for cls in self.classes:
            # Create an instance
            inst = cls(config=self.config)
            # Get parameters back
            self.config.setdefault(cls.__name__, Config())
            for name, value in inst.trait_values(config=True).items():
                self.config[cls.__name__][name] = value

        # First parse CLI (for help for instance, or specify the config files)
        self.parse_command_line(argv)

        # Read config files (done last but hasn't priority over CLI)
        if self.config_file:
            self.load_config_file(self.config_file)

    def _create_loader(self, argv, aliases, flags, classes):
        return StrictArgParse(
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

    def write_config(self, filename: str | None = None):
        """(Over)write a configuration file.

        Parameters
        ----------
        filename:
            Write to this file. If None, the current value of
            :attr:`config_file` is used.
        """
        lines = self.generate_config_file().splitlines()
        # Remove trailing whitespace
        lines = [line.rstrip() for line in lines]

        if filename is None:
            filename = self.config_file
        with open(filename, 'w') as f:
            f.write('\n'.join(lines))
