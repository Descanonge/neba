"""Writer module: write data to disk."""

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
from os import path

from neba.config.loaders.json import JsonEncoderTypes

from .module import Module
from .types import T_Data, T_Source, T_Source_contra

log = logging.getLogger(__name__)


class WriterAbstract(t.Generic[T_Source_contra, T_Data], Module):
    """Abstract class of Writer module.

    Manages metadata to (eventually) add to data before writing.
    """

    metadata_params_exclude: abc.Sequence[str] = ["dask.", "log_"]
    """Prefixes of parameters to exclude from metadata attribute."""

    metadata_git_ignore: abc.Sequence[str] = []
    """Files and folders to ignore when creating git diff."""

    metadata_max_diff_lines = 30
    """Maximum number of lines to include in diff."""

    def add_git_metadata(self, script: str, meta: dict[str, t.Any]) -> None:
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
        add_interface_params: bool = True,
        add_commit: bool = True,
    ) -> dict[str, t.Any]:
        """Get information on how data was created.

        Attributes are:

        * ``written_with_interface``: name of interface class.
        * ``created_by``: hostname and filename of the python script used
        * ``created_with_params``: a string representing the parameters,
        * ``created_on``: date of creation
        * ``created_at_commit``: if found, the HEAD commit hash.
        * ``git_diff_short``: if workdir is dirty, a list of modified files
        * ``git_diff_long``: if workdir is dirty, the full diff (truncated) at
          :attr:`metadata_max_diff_lines`.

        Parameters
        ----------
        add_interface_params
            If True (default), add the parent interface parameters to metadata.
            Parameters are converted to a dictionary are serialized using json, and if
            that fails `str()`.
        add_commit
            If True (default), add the current commit hash of the directory
            containing the script
        """
        meta = {}

        # Name of class
        cls_name = self.di.__class__.__name__
        if self.di.ID:
            cls_name += f":{self.di.ID}"
        meta["written_with_interface"] = cls_name

        # Get hostname and script name
        hostname = socket.gethostname()
        script = ""
        for stack in inspect.stack():
            if "neba" not in stack.filename:
                script = stack.filename
                break

        meta["created_by"] = f"{hostname}:{script}"

        # Get parameters as string
        if add_interface_params:
            # copy / convert to dict
            params = dict(self.di.parameters.direct)
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

    def write(
        self,
        data: T_Data | abc.Sequence[T_Data],
        target: T_Source_contra | abc.Sequence[T_Source_contra] | None = None,
        **kwargs: t.Any,
    ) -> t.Any:
        """Write data to file or store.

        :Not implemented: implement in a module subclass.

        Parameters
        ----------
        data
            Data to write.
        target
            If None, target location(s) should be obtained via
            :meth:`.DataInterface.get_source`.
        """
        raise NotImplementedError("Implement in a module subclass.")

    def check_directories(
        self, calls: abc.Sequence[tuple[T_Source_contra, T_Data]]
    ) -> None:
        """Check if directories are missing, and create them if necessary."""
        files = [f for f, _ in calls]

        # Keep only the containing directories, with no duplicate
        directories = set()
        for f in files:
            directories.add(path.dirname(t.cast(str | os.PathLike, f)))

        for d in directories:
            if not path.isdir(d):
                log.debug("Creating output directory %s", d)
                os.makedirs(d)

    def check_directory(self, call: tuple[T_Source_contra, T_Data]) -> None:
        """Check if directory is missing, and create it if necessary."""
        self.check_directories([call])

    def check_overwriting_calls(
        self, calls: abc.Sequence[tuple[T_Source_contra, T_Data]]
    ) -> None:
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

    def send_single_call(
        self, call: tuple[T_Source_contra, T_Data], **kwargs: t.Any
    ) -> t.Any:
        """Execute a single call.

        :Not implemented: implement in a module subclass.

        Parameters
        ----------
        kwargs
            Passed to the writing function.
        """
        raise NotImplementedError("Implement in a module subclass.")

    def send_calls(
        self, calls: abc.Sequence[tuple[T_Source_contra, T_Data]], **kwargs: t.Any
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


T = t.TypeVar("T", covariant=True)


@t.runtime_checkable
class Splitable(t.Protocol[T]):
    """Protocol for a source module that can split data into multiple sources.

    A number of parameters can be left :meth:`unfixed` which results in multiple files
    (for instance, if we do not "fix" the parameter *year*, we can have files for any
    year we want).

    It must also implement a :meth:`get_filename` method that returns a filename when
    given a specific set of values.

    The idea is that a module can split data according to the parameters that are left
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

    def get_filename(self, **fixes: t.Any) -> T:
        """Return a filename corresponding to this set of values.

        This must also take into account values that are already specified in the
        data-manager parameters (that are not present in the *fixes* argument).
        """


class SplitWriterMixin(WriterAbstract[T_Source, T_Data]):
    """Split data to multiple writing targets.

    For that, we need to have an appropriate Source module that adheres to the
    :class:`Splitable` protocol. This mixin checks this. It makes available the
    necessary methods directly to the Writer module.
    """

    source: Splitable[T_Source]

    def setup(self) -> None:
        """Set up module. Check the source is following the Splitable protocol."""
        super().setup()

        if not isinstance(self.di.source, Splitable):
            raise TypeError(f"Source module is not Splitable ({type(self.di)})")
        self.source = self.di.source

    def unfixed(self) -> set[T_Source]:
        """Return set of parameters that are not fixed."""
        return set(self.source.unfixed)

    def get_filename(self, **kwargs: t.Any) -> T_Source:
        """Return a filename corresponding to current parameters and kwargs."""
        return self.source.get_filename(**kwargs)
