"""Writer plugin: write data to disk."""

from __future__ import annotations

import inspect
import json
import logging
import os
import socket
import subprocess
import typing as t
from collections import abc
from datetime import datetime
from os import PathLike, path

from .data_manager import Plugin, T_Data, T_Source
from .loader import LoaderPluginAbstract

log = logging.getLogger(__name__)


class WriterPluginAbstract(t.Generic[T_Source, T_Data], Plugin):
    """Abstract class of Writer plugin.

    Manages metadata to (eventually) add to data before writing.
    """

    def get_metadata(
        self,
        add_dataset_params: bool = True,
        add_commit: bool = True,
    ) -> dict[str, t.Any]:
        """Set some dataset attributes with information on how it was created.

        Attributes are:

        * ``written_as_dataset``: name of dataset class.
        * ``created_by``: hostname and filename of the python script used
        * ``created_with_params``: a string representing the parameters,
        * ``created_on``: date of creation
        * ``created_at_commit``: if found, the current/HEAD commit hash.

        Parameters
        ----------
        params
            A dictionnary of the parameters used, that will automatically be serialized
            as a string. Can also be a custom string.
            Presentely we first try a serialization using json, if that fails, `str()`.
        add_dataset_params
            If True (default), add the parent dataset parameters values to metadata.
            Parameters "as dict" are serialized using json, and if that fails `str()`.
        add_commit
            If True (default), try to find the current commit hash of the directory
            containing the script called.
        """
        meta = {}

        # Name of class
        cls_name = self.__class__.__name__
        if self.ID:
            cls_name += f":{self.ID}"
        meta["written_as_dataset"] = cls_name

        # Get hostname and script name
        hostname = socket.gethostname()
        script = inspect.stack()[1].filename
        meta["created_by"] = f"{hostname}:{script}"

        # Get parameters as string
        if add_dataset_params:
            params = self.params_as_dict
            try:
                params_str = json.dumps(params)
            except TypeError:
                params_str = str(params)

            meta["created_with_params"] = params_str

        # Get date
        meta["created_on"] = datetime.today().strftime("%x %X")

        # Get commit hash
        if add_commit:
            # Use the directory of the calling script
            gitdir = path.dirname(script)
            cmd = ["git", "-C", gitdir, "rev-parse", "HEAD"]
            ret = subprocess.run(cmd, capture_output=True, text=True)
            if ret.returncode == 0:
                commit = ret.stdout.strip()
                meta["created_at_commit"] = commit
            else:
                log.debug("'%s' not a valid git directory", gitdir)

        return meta

    def check_directories(self, calls: abc.Sequence[tuple[T_Source, T_Data]]):
        """Check if directories are missing, and create them if necessary."""
        files = [f for f, _ in calls]

        # Keep only the containing directories, with no duplicate
        directories = set()
        for f in files:
            assert isinstance(f, str | PathLike)
            directories.add(path.dirname(f))

        for d in directories:
            if not path.isdir(d):
                log.debug("Creating output directory %s", d)
                os.makedirs(d)

    def check_directory(self, call: tuple[T_Source, T_Data]):
        """Check if directory is missing, and create it if necessary."""
        self.check_directories([call])

    def send_single_call(self, call: tuple[T_Source, T_Data], **kwargs) -> t.Any:
        """Execute a single call.

        :Not implemented: implement in plugin subclass.

        Parameters
        ----------
        kwargs
            Passed to the writing function.
        """
        raise NotImplementedError("Implement in plugin subclass.")

    def check_overwriting_calls(self, calls: abc.Sequence[tuple[T_Source, T_Data]]):
        """Check if some calls have the same filename."""
        outfiles = [f for f, _ in calls]
        duplicates = []
        for f in set(outfiles):
            if outfiles.count(f) > 1:
                duplicates.append(f)

        if duplicates:
            raise ValueError(
                f"Multiple writing calls to the same filename·s: {duplicates}"
            )

    def send_calls(self, calls: abc.Sequence[tuple[T_Source, T_Data]], **kwargs):
        """Send multiple calls serially.

        Check beforehand if there are filename conflicts betwen calls, and make
        sure the necessary (sub)directories are created if they not exist already.

        Parameters
        ----------
        kwargs
            Passed to writing function.
        """
        self.check_overwriting_calls(calls)
        self.check_directories(calls)

        for call in calls:
            self.send_single_call(call, **kwargs)

    def write(
        self,
        data: T_Data | abc.Sequence[T_Data],
        target: T_Source | None = None,
        **kwargs,
    ) -> t.Any:
        """Write data to file or store.

        :Not implemented: implement in plugin subclass.

        Parameters
        ----------
        data
            Data to write.
        target
            If None, target location(s) should be obtained via
            :meth:`.DataManagerBase.get_source`.
        """
        raise NotImplementedError("Implement in plugin subclass.")


class CachedWriterPlugin(
    WriterPluginAbstract[T_Source, T_Data], LoaderPluginAbstract[T_Source, T_Data]
):
    """Generate data and save it to source if it does not already exist.

    When loading data (with :meth:`get_data`), if the source does not exist:

    * generate the data with :meth:`generate_data` (to be defined by the user)
    * write it to the source with :meth:`_write_cached_data` which by default simply
      calls ``write()`` but can be specialized in a subclass.
    * load the data back from the source using
      :meth:`super().get_data<.loader.LoaderPluginAbstract.get_data>` which will apply
      post-processing if defined.

    If you use a loader plugin subclass that overwrites ``get_data()`` it should be
    placed **after** ``CachedWriterPlugin`` in the data manager bases. The placement of
    the writer plugin is not constrained::

        class MyDataManager(
            WriterPlugin, CachedWriterPlugin, LoaderPlugin, SourcePlugin, DataManagerBase
        ):
            def generate_data():
                ...
    """

    def generate_data(self) -> T_Data:
        """Generate data.

        This function will be used to obtain data if it is not found in the source (ie
        in a file or data store). It will automatically be written to that source.

        :Not implemented: implement in your DataManager subclass.

        """
        raise NotImplementedError("Implement in your DataManager subclass.")

    def get_data(self, /, *, source: T_Source | None = None, **kwargs) -> T_Data:
        """Load or generate data.

        Parameters
        ----------
        source
            Source location of the data to load. If left to None,
            :meth:`~.data_manager.DataManagerBase.get_source` is used.
        """
        if source is None:
            source = self.get_source()

        if not self._source_exists(source):
            data = self.generate_data()
            self._write_cached_data(source, data)

        return super().get_data(source=source, **kwargs)

    def _source_exists(self, source: T_Source) -> bool:
        """Return if given source exists.

        If not, the data will be generated. By default, check for existence of a single
        file.
        """
        return path.isfile(t.cast(str, source))

    def _write_cached_data(self, source: T_Source, data: T_Data):
        """Write generated data to source.

        By default simply call :meth:`~WriterPluginAbstract.write`. This method can be
        specialized in subclasses.

        """
        self.write(data, target=source)
