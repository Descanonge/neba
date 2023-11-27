import os
from os import path

from filefinder import Finder

from .util import Assistant


class FileManager(Assistant):
    """Multifiles manager using Filefinder.

    Maybe add the signature of methods to override in rst ?
    """

    METHODS_TO_DEFINE = ['get_root_directory', 'get_filename_pattern']

    def __str__(self):
        s = [
            f'Root directory: {self.root_directory}',
            f'Filename pattern: {self.filename_pattern}',
        ]
        return '\n'.join(s)

    def __init__(self, dataset):
        super().__init__(dataset)

        self.define_auto_cache('filefinder', self.get_filefinder)
        self.define_auto_cache('fixable_params', self.find_fixable_params)
        self.define_auto_cache('datafiles', self.get_datafiles)

        # Add fixable_params to the dataset allowed_params
        fixable = self.get_cached('fixable_params')
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
    def filefinder(self) -> Finder:
        """Filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.

        This property is the cached result of :func:`get_filefinder`.
        """
        finder: Finder = self.get_cached('filefinder')
        fixable_params = self.get_cached('fixable_params')

        for p, value in self.dataset.params.items():
            if p in fixable_params:
                finder.fix_group(p, value)

        return finder

    def get_filefinder(self) -> Finder:
        """Return a filefinder instance to scan for datafiles.

        Is also used to create filenames for a specific set of parameters.
        """
        finder = Finder(self.root_directory, self.filename_pattern)
        return finder

    @property
    def fixable_params(self) -> list[str]:
        """List of parameters that vary in the filefinder object.

        Found automatically from a :attr:`filefinder` instance.
        This property is the cached result of :func:`find_fixable_params`.
        """
        return self.get_cached('fixable_params')

    def find_fixable_params(self) -> list[str]:
        """Find parameters that vary in the filename pattern.

        Automatically find them using a :class:`Finder` instance.
        """
        finder: Finder = self.get_cached('filefinder')
        groups_names = [g.name for g in finder.groups]
        # remove doublons
        return list(set(groups_names))

    @property
    def datafiles(self) -> list[str]:
        """List of datafiles to open.

        This property is the cached result of :func:`get_datafiles`.
        """
        return self.get_cached('datafiles')

    def get_datafiles(self) -> list[str]:
        """Scan and return files corresponding to pattern.

        Use the :attr:`filefinder` object to scan for files corresponding to
        the filename pattern.
        """
        return self.get_cached('filefinder').get_files()

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

        self.dataset._check_param_known(fixes)
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
