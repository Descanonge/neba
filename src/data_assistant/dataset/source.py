"""FileManager module."""
from __future__ import annotations

import logging
from os import path

from .module import CacheModule, autocached

log = logging.getLogger(__name__)


class MultiFileModuleAbstract(CacheModule):
    def get_filename(self, **fixes) -> str:
        # not necessary if we only want to upload data :/
        # Use a protocol or force check hasattr in WriterModules ?
        raise NotImplementedError()

    def get_root_directory(self) -> str | list[str]:
        # Not necessary either, just in their for some common code
        raise NotImplementedError()

    @property
    def root_directory(self) -> str:
        """Root directory containing data."""
        rootdir = self.get_root_directory()

        if isinstance(rootdir, list | tuple):
            rootdir = path.join(*rootdir)

        return rootdir

    def get_source(self) -> list[str]:
        return self.datafiles

    @property
    @autocached
    def datafiles(self) -> list[str]:
        raise NotImplementedError()


class GlobModule(MultiFileModuleAbstract, CacheModule):
    def get_glob_pattern(self):
        raise NotImplementedError("Implement in your Dataset subclass.")

    @property
    @autocached
    def datafiles(self) -> list[str]:
        import glob

        try:
            root = self.root_directory
        except NotImplementedError:
            root = None

        pattern = self.get_glob_pattern()
        files = glob.glob(pattern, root_dir=root, recursive=True)

        if len(files) == 0:
            log.warning("No file found for pattern %s", pattern)
        return files
