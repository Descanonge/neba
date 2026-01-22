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

from data_assistant.config.loaders.json import JsonEncoderTypes

from .loader import LoaderAbstract
from .module import Module
from .util import T_Data, T_Source

log = logging.getLogger(__name__)


class WriterAbstract(t.Generic[T_Source, T_Data], Module):
    """Abstract class of Writer plugin.

    Manages metadata to (eventually) add to data before writing.
    """

    metadata_params_exclude: abc.Sequence[str] = ["dask.", "log_"]
    """Prefixes of parameters to exclude from metadata attribute."""

    metadata_git_ignore: abc.Sequence[str] = []
    """Files and folders to ignore when creating git diff."""

    metadata_max_diff_lines = 30
    """Maximum number of lines to include in diff."""

    def add_git_metadata(self, script: str, meta: dict[str, t.Any]):
        """Add git information to meta dictionary."""
        # use the directory of the calling script
        gitdir = path.dirname(script) if script else "."

        # check if script is in a git directory and get current commit
        cmd = ["git", "-C", gitdir, "rev-parse", "HEAD"]
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode != 0:
            log.debug("'%s' not a valid git directory", gitdir)
            return
        commit = ret.stdout.strip()
        meta["created_at_commit"] = commit

        # get top level (necessary for exclude arguments)
        gitdir = subprocess.run(
            ["git", "-C", gitdir, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        ).stdout.strip()

        # check if there is diff
        diffcmd = [
            "git",
            "-C",
            gitdir,
            "--no-pager",
            "diff",
            "-w",
            "--diff-filter=M",
            "--minimal",
        ]
        exclude_cmd = [f":!{x}" for x in self.metadata_git_ignore]
        cmd = diffcmd + ["--numstat"] + exclude_cmd
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode != 0:
            err = ret.stderr.strip()
            if (stop := err.find("usage:")) > 0:
                err = err[:stop]
            log.warning("Error in creating diff, [%s]\n (%s)", ret.stderr.strip())
            return
        stat = ret.stdout.strip()
        if stat:
            stat_lines = []
            for line in stat.splitlines():
                plus, minus, filename = line.split("\t")
                stat_lines.append(f"{filename}:+{plus}:-{minus}")
            meta["git_diff_short"] = stat_lines

            # add full diff
            cmd = diffcmd + ["--unified=0"] + exclude_cmd
            ret = subprocess.run(cmd, capture_output=True, text=True)
            if ret.returncode != 0:
                err = ret.stderr.strip()
                if (stop := err.find("usage:")) > 0:
                    err = err[:stop]
                log.warning("Error in creating diff, [%s]\n (%s)", ret.stderr.strip())
                return
            diff = ret.stdout.strip().splitlines()
            if (n := len(diff)) > (m := self.metadata_max_diff_lines):
                diff = diff[:m]
                diff.append(f"... {n - m} additional lines")
            meta["git_diff_long"] = diff

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
        * ``git_diff_short``: if workdir is dirty, a list of modified files
        * ``git_diff_long``: if workdir is dirty, the full diff (truncated) at
          :attr:`metadata_max_diff_lines`.

        Parameters
        ----------
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
        if self.dm.ID:
            cls_name += f":{self.dm.ID}"
        meta["written_as_dataset"] = cls_name

        # Get hostname and script name
        hostname = socket.gethostname()
        script = ""
        for stack in inspect.stack():
            if "data_assistant" not in stack.filename:
                script = stack.filename
                break

        meta["created_by"] = f"{hostname}:{script}"

        # Get parameters as string
        if add_dataset_params:
            # copy / convert to dict
            params = dict(self.dm.params)
            for prefix in self.metadata_params_exclude:
                params = {k: v for k, v in params.items() if not k.startswith(prefix)}
            try:
                params_str = json.dumps(params, cls=JsonEncoderTypes)
            except TypeError:
                params_str = str(params)

            meta["created_with_params"] = params_str

        # Get date
        meta["created_on"] = datetime.today().strftime("%x %X")

        # Get commit hash
        if add_commit:
            self.add_git_metadata(script, meta)

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

    def send_calls(
        self, calls: abc.Sequence[tuple[T_Source, T_Data]], **kwargs
    ) -> list[t.Any]:
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

        return [self.send_single_call(call, **kwargs) for call in calls]

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


class CachedWriter(WriterAbstract[T_Source, T_Data], LoaderAbstract[T_Source, T_Data]):
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
            source = self.dm.get_source()

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


T = t.TypeVar("T", covariant=True)


@t.runtime_checkable
class Splitable(t.Protocol[T]):
    """Protocol for a source plugin that can split data into multiple sources.

    The plugin manages input/output sources. Initially made for multifile datasets.
    A number of parameters can be left :meth:`unfixed` which allows to have many files
    (for instance, if we do not "fix" the parameter *year*, we can have files for any
    year we want).

    It must also implement a :meth:`get_filename` method that returns a filename when
    given a specific set of values (those that were left unfixed).

    The idea is that a plugin can split data according to the parameters that are left
    unfixed (example by year), once the data is split we find the associated filename
    for each year and we then write to files.

    The protocol is generic and allows for any type of source.
    """

    @property
    def unfixed(self) -> abc.Iterable[T]:
        """Iterable of parameters that are not fixed.

        This must take into account the values that are specified (or not) in the
        data-manager parameters.
        """
        ...

    def get_filename(self, **fixes: t.Any) -> T:
        """Return a filename corresponding to this set of values.

        This must also take into account values that are already specified in the
        data-manager parameters (that are not present in the *fixes* argument).
        """


class SplitWriterMixin(WriterAbstract[T_Source, T_Data]):
    """Split data to multiple writing targets.

    For that, we need to have an appropriate Source module, that adheres to the
    :class:`Splitable` protocol. This mixin checks this. It makes available the
    necessary methods directly to the Writer module.
    """

    source: Splitable[T_Source]

    def setup(self):
        super().setup()

        if not isinstance(self.dm.source, Splitable):
            raise TypeError(f"Source module is not Splitable ({type(self.dm)})")
        self.source = self.dm.source

    def unfixed(self) -> set[T_Source]:
        return set(self.source.unfixed)

    def get_filename(self, **kwargs) -> T_Source:
        return self.source.get_filename(**kwargs)
