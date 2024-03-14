"""Writer plugin: write data to disk."""

from __future__ import annotations

import inspect
import json
import logging
import os
import socket
import subprocess
from collections.abc import Sequence
from datetime import datetime
from os import path
from typing import Any

from .data_manager import Plugin, _DataT

Call = tuple[_DataT, str]
"""Tuple of data and filename to write it to."""

log = logging.getLogger(__name__)


class WriterPluginAbstract(Plugin):
    """Abstract class of Writer plugin.

    Manages metadata to (eventually) add to data before writing.
    """

    def get_metadata(
        self,
        params: dict | str | None = None,
        add_dataset_params: bool = True,
        add_commit: bool = True,
    ) -> dict[str, Any]:
        """Set some dataset attributes with information on how it was created.

        Attributes are:

        * ``written_as_dataset:`` name of dataset class.
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
            Add the parent dataset parameters values to serialization if True (default)
            and if ``parameters`` is not a string. The parent parameters won't overwrite
            the values of ``parameters``.
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
        if params is not None:
            if isinstance(params, str):
                params_str = params
            else:
                if add_dataset_params:
                    params = self.params | params
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

    def check_directories(self, calls: Call | Sequence[Call]):
        """Check if directories are missing, and create them if necessary."""
        if isinstance(calls, tuple):
            calls = [calls]
        files = [f for _, f in calls]

        # Keep only the containing directories, with no duplicate
        directories = set()
        for f in files:
            directories.add(path.dirname(f))

        for d in directories:
            if not path.isdir(d):
                log.debug("Creating output directory %s", d)
                os.makedirs(d)

    def send_single_call(self, call, **kwargs) -> Any:
        """Execute a single call.

        Parameters
        ----------
        kwargs
            Passed to the writing function.

        *Not implemented: implement in a plugin subclass.*
        """
        raise NotImplementedError("Implement this method in a plugin subclass.")


class WriterMultiFileAbstract(WriterPluginAbstract):
    """Add basic functionalities for multifile datasets.

    Allow to deal with multiple calls: check if there is some conflict of filename
    between calls, and a method to send calls one after another.
    """

    def check_overwriting_calls(self, calls: Sequence[Call]):
        """Check if some calls have the same filename."""
        outfiles = [f for _, f in calls]
        duplicates = []
        for f in set(outfiles):
            if outfiles.count(f) > 1:
                duplicates.append(f)

        if duplicates:
            raise ValueError(
                f"Multiple writing calls to the same filename·s: {duplicates}"
            )

    def send_calls(self, calls: Sequence[Call], **kwargs):
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
