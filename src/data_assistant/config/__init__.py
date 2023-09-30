from collections.abc import Sequence

from traitlets import Unicode
from traitlets.config import Application
from traitlets.config.loader import KVArgParseConfigLoader, Config, DeferredConfig

from .dask_config import DaskClusterPBS, DaskClusterSLURM
from .parameters import Parameters


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
                    self.parser.error(f"DeferredConfig not allowed / undefined trait '{fullkey}'")

        config = super().load_config(argv=argv, aliases=aliases, classes=classes)
        check_config(config, 'c')
        return config


class App(Application):
    classes = [Parameters, DaskClusterPBS, DaskClusterSLURM]

    config_file = Unicode(
        'config.py', help='Load this config file'
    ).tag(config=True)

    def initialize(self, argv=None):
        self.parse_command_line(argv)
        if self.config_file:
            self.load_config_file(self.config_file)

        self.parameters = Parameters(config=self.config)
        self.daskclusterSLURM = DaskClusterSLURM(config=self.config)

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

    def get_params(self, select: Sequence[str] | None = None):
        params = self.parameters.trait_values(config=True)
        if select is None:
            return params

        for p in select:
            if p not in params:
                raise KeyError(f"Trait '{p}' not found in parameters.")
        return {p: params[p] for p in select}

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


if __name__ == '__main__':
    app = Config()
    app.initialize()
