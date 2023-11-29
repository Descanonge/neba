import logging
import os
from os import path

from filefinder import Finder

from .module import Module, autocached

log = logging.getLogger(__name__)


class FileManagerAbstract(Module):
    @property
    def datafiles(self) -> list[str]:
        """Get available datafiles."""
        raise NotImplementedError('Subclass must implement this method.')

    def get_filename(self, **fixes) -> str:
        """Create a filename corresponding to a set of parameters values.

        All parameters must be defined, either with the instance :attr:`params`,
        or with the ``fixes`` arguments.

        Parameters
        ----------
        fixes:
            Parameters to fix to specific values. Override :attr:`params` values.
        """
        raise NotImplementedError('Subclass must implement this method.')


class FileFinderManager(FileManagerAbstract):
    """Multifiles manager using Filefinder.

    Maybe add the signature of methods to override in rst ?
    """

    TO_DEFINE_ON_DATASET = ['get_root_directory', 'get_filename_pattern']

    def __str__(self):
        s = [
            f'Root directory: {self.root_directory}',
            f'Filename pattern: {self.filename_pattern}',
        ]
        return '\n'.join(s)

    def __init__(self, dataset):
        super().__init__(dataset)

        # Add fixable_params to the dataset allowed_params
        fixable = self.fixable_params
        self.dataset.allowed_params |= set(fixable)

    @property
    def root_directory(self) -> str:
        """Root directory containing data."""
        rootdir = self.run_on_dataset('get_root_directory')

        if not isinstance(rootdir, str | os.PathLike):
            rootdir = path.join(*rootdir)

        return rootdir

    @property
    def filename_pattern(self) -> str:
        """Filename pattern used to find files using :mod:`filefinder`."""
        return self.run_on_dataset('get_filename_pattern')

    @property
    @autocached
    def filefinder(self) -> Finder:
        """Filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.

        This property is the cached result of :func:`get_filefinder`.
        """
        finder = Finder(self.root_directory, self.filename_pattern)
        # cache this temporary finder to avoid infinite recursion when
        # getting fixable_params (which needs a Finder)
        self.cache['filefinder'] = finder
        fixable_params = self.fixable_params

        for p, value in self.dataset.params.items():
            if p in fixable_params:
                finder.fix_group(p, value)

        return finder

    def get_filefinder(self) -> Finder:
        """Return a filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.
        """

    @property
    @autocached
    def fixable_params(self) -> list[str]:
        """List of parameters that vary in the filefinder object.

        Found automatically from a :class:`filefinder.Finder` instance.
        """
        finder = self.filefinder
        groups_names = [g.name for g in finder.groups]
        # remove doublons
        return list(set(groups_names))

    @property
    @autocached
    def datafiles(self) -> list[str]:
        """Datafiles available.

        Use the :attr:`filefinder` object to scan for files corresponding to
        the filename pattern.
        """
        files = self.filefinder.get_files()
        if len(files) == 0:
            log.warning('%s', self.filefinder)
        return files

    def get_filename(self, **fixes) -> str:
        """Create a filename corresponding to a set of parameters values.

        All parameters must be defined, with the instance :attr:`params`,
        or with the ``fixes`` arguments.

        Parameters
        ----------
        fixes:
            Parameters to fix to specific values. Only parameters defined in the
            filename pattern can be fixed. Will take precedence over the
            instance :attr:`params` attribute.
        """
        finder: Finder = self.get_cached('filefinder')
        fixable: list[str] = self.get_cached('fixable_params')

        self.dataset.check_known_param(fixes)
        # Check they can be fixed (they exist in the pattern)
        for f in fixes:
            if f not in fixable:
                raise KeyError(f'Parameter {f} cannot be fixed.')

        # In case params were changed sneakily and the cache was not invalidated
        fixable_params = {
            p: value for p, value in self.dataset.params.items() if p in fixable
        }
        fixes.update(fixable_params)
        filename = finder.make_filename(fixes)
        return filename
