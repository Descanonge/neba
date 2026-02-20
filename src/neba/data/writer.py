"""Writer module: write data to disk."""

from __future__ import annotations

import inspect
import json
import logging
import os
import socket
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from os import path
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Protocol,
    TypeVar,
    cast,
    runtime_checkable,
)

from traitlets import Bool, Int, List, Unicode

from neba.config import Section
from neba.config.loaders.json import JsonEncoderTypes
from neba.utils import get_classname

from .module import Module
from .types import T_Data, T_Source, T_Source_contra

if TYPE_CHECKING:
    from .interface import DataInterface


log = logging.getLogger(__name__)


class MetadataOptions(Section):
    """Options for metadata generator."""

    elements = List(
        Unicode(),
        default_value=[
            "written_with_interface",
            "creation_time",
            "creation_script",
            "creation_hostname",
            "creation_params_str",
            "creation_commit",
            "creation_diff",
        ],
    )

    elements_to_skip = {
        "add_params": ["creation_params", "creation_params_str"],
        "add_git_info": ["creation_commit", "creation_diff"],
    }
    """Mapping from traits to lists of elements. If the trait is False, those
    elements will be skipped."""

    add_params = Bool(True, help="If True add parameters (either as dict or str).")
    add_git_info = Bool(
        True, help="If True add information about git repository status."
    )

    # -- Other parameters --

    params_exclude = List(
        Unicode(),
        default_value=["log_"],
        help="Prefixes of parameters to exclude from metadata attribute.",
    )

    max_diff_lines = Int(30, help="Maximum number of lines to include in diff.")

    creation_script = Unicode(
        None,
        allow_none=True,
        help="Manually specify the creation script.",
    )

    git_ignore = List(
        Unicode(),
        default_value=[],
        help="Files and folders to ignore when creating git diff.",
    )

    def get_elements(self) -> list[str]:
        """Return elements (skipping thoses not selected by user)."""
        elements_to_skip = []
        for selector_option, to_skip in self.elements_to_skip.items():
            if not getattr(self, selector_option):
                elements_to_skip += to_skip

        return [elt for elt in self.elements if elt not in elements_to_skip]


class MetadataGenerator:
    """Generate metadata from Interface.

    Options are stored in an instance of :attr:`options_cls`.

    Metadata is split into elements. Each element corresponds to a method in this class,
    that when run will add stuff to a metadata dictionary. The user can specify elements
    to run via the :attr:`~.MetadataOptions.elements` trait, or skip groups of elements
    by passing the parameters specified in :attr:`~.MetadataOptions.elements_to_skip`.

    If an element returns a value when run, it will be added to the metadata dictionary
    with that element name. Otherwise, the element can add to the metadata attribute
    itself (maybe multiple items) and return None.

    If an error is raised when running an element, the exception is only logged and
    the generation continues.

    When all elements have run, the :meth:`postprocess` method is run. This is a good
    place to slightly modify the metadata, like for renaming some items.

    Parameters
    ----------
    di
        The parent DataInterface.
    kwargs
        Options passed to :attr:`options_cls`.
    """

    options_cls = MetadataOptions

    def __init__(self, di: DataInterface, **kwargs: Any) -> None:
        self.di: DataInterface = di
        self.metadata: dict[str, Any] = {}
        self.options = self.options_cls(**kwargs)

    def generate(self) -> dict[str, Any]:
        """Generate metadata."""
        for name in self.options.get_elements():
            if not hasattr(self, name):
                raise AttributeError(f"No metadata property named '{name}'")

            try:
                element = getattr(self, name)()
                if element is not None:
                    self.metadata[name] = element
            except Exception as exc:
                log.warning("Failed to retrieved metadata element '%s' (%s)", name, exc)
                continue

        self.postprocess()

        return self.metadata

    def postprocess(self) -> None:
        """Modify the metadata attribute in place, after generation."""
        pass

    def written_with_interface(self) -> str:
        """Class-name and ID of parent interface."""
        cls_name = get_classname(self.di)
        if self.di.ID:
            cls_name += f":{self.di.ID}"
        return cls_name

    def creation_time(self) -> str:
        """Date and time."""
        return datetime.today().strftime("%x %X")

    def creation_hostname(self) -> str:
        """Return hostname of current running process."""
        return socket.gethostname()

    def creation_script(self) -> str:
        """Filename of top-level script or notebook."""
        if self.options.creation_script is not None:
            return self.options.creation_script

        # check if in Jupyter session
        try:
            import IPython
        except ImportError:
            pass
        else:
            ip = IPython.get_ipython()
            if (
                ip is not None
                and (session := ip.user_ns.get("__session__")) is not None
                and session.endswith(".ipynb")  # could be a console
            ):
                return session

        script = None
        for stack in inspect.stack():
            # we can still be in a IPython console
            if "IPython" in stack.filename:
                break
            script = stack.filename

        if script is None:
            raise ValueError

        return script

    def creation_params(self) -> dict[str, Any]:
        """Return interface parameters as dictionary."""
        # This should work for dict and Section, but not necessarily for future
        # parameters containers
        params = dict(self.di.parameters.direct)
        for prefix in self.options.params_exclude:
            params = {k: v for k, v in params.items() if not k.startswith(prefix)}

        return params

    def creation_params_str(self) -> None:
        """Return interface parameters as string serialized by JSON.

        Store them in ``creation_params``.
        """
        params = self.creation_params()
        self.metadata["creation_params"] = json.dumps(params, cls=JsonEncoderTypes)

    def creation_commit(self) -> str:
        """Return latest commit hash."""
        # use the directory of the calling script
        gitdir = path.dirname(self.metadata.get("creation_script", "."))

        cmd = ["git", "-C", gitdir, "rev-parse", "HEAD"]
        ret = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return ret.stdout.strip()

    def creation_diff(self) -> None:
        """Add git diff, only if latest commit hash is present."""
        if "creation_commit" not in self.metadata:
            return

        def git_cmd(cmd: list[str]) -> str:
            """Execute git command with informative log message."""
            ret = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if ret.returncode != 0:
                err = ret.stderr.strip()
                if (stop := err.find("usage:")) > 0:
                    err = err[:stop]
                msg = f"Error in creating git diff with command {' '.join(cmd)}\n{err}"
                log.warning(msg)
                raise RuntimeError
            return ret.stdout.strip()

        # use the directory of the calling script
        gitdir = path.dirname(self.metadata.get("creation_script", "."))

        # get top level (necessary for exclude arguments)
        gitdir = git_cmd(["git", "-C", gitdir, "rev-parse", "--show-toplevel"])

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
        exclude_cmd = [f":!{x}" for x in self.options.git_ignore]

        stat = git_cmd(diffcmd + ["--numstat"] + exclude_cmd)
        if stat:
            stat_lines = []
            for line in stat.splitlines():
                plus, minus, filename = line.split("\t")
                stat_lines.append(f"{filename}:+{plus}:-{minus}")
            self.metadata["creation_diff_short"] = stat_lines

            # add full diff
            diff = git_cmd(diffcmd + ["--unified=0"] + exclude_cmd).splitlines()
            if (n := len(diff)) > (m := self.options.max_diff_lines):
                diff = diff[:m]
                diff.append(f"... {n - m} additional lines")
            self.metadata["git_diff_long"] = diff


class WriterAbstract(Generic[T_Source_contra, T_Data], Module):
    """Abstract class of Writer module."""

    metadata_generator = MetadataGenerator

    def get_metadata(self, **kwargs: Any) -> dict[str, Any]:
        """Get information on how data was created.

        Uses :attr:`metadata_generator`.

        Parameters
        ----------
        kwargs
            Options passed to :class:`MetadataOptions`
        """
        generator = self.metadata_generator(self.di, **kwargs)
        return generator.generate()

        # # Get parameters as string
        # if add_interface_params:
        #     # copy / convert to dict
        #     params = dict(self.di.parameters.direct)
        #     for prefix in self.metadata_params_exclude:
        #         params = {k: v for k, v in params.items() if not k.startswith(prefix)}
        #     try:
        #         params_str = json.dumps(params, cls=JsonEncoderTypes)
        #     except TypeError:
        #         params_str = str(params)

        #     meta["created_with_params"] = params_str

        # # Get date
        # meta["created_on"] = datetime.today().strftime("%x %X")

        # # Get commit hash
        # if add_commit:
        #     self.add_git_metadata(script, meta)

        # return meta

    def write(
        self,
        data: T_Data | Sequence[T_Data],
        target: T_Source_contra | Sequence[T_Source_contra] | None = None,
        metadata_kwargs: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Write data to file or store.

        :Not implemented: implement in a module subclass.

        Parameters
        ----------
        data
            Data to write.
        target
            If None, target location(s) should be obtained via
            :meth:`.DataInterface.get_source`.
        metadata_kwargs
            Passed to the :attr:`metadata_generator`. See :class:`.MetadataOptions` for
            available options.
        kwargs
            Passed to the writing function.
        """
        raise NotImplementedError("Implement in a module subclass.")

    def check_directories(
        self, calls: Sequence[tuple[T_Source_contra, T_Data]]
    ) -> None:
        """Check if directories are missing, and create them if necessary."""
        files = [f for f, _ in calls]

        # Keep only the containing directories, with no duplicate
        directories = set()
        for f in files:
            directories.add(path.dirname(cast(str | os.PathLike, f)))

        for d in directories:
            if not path.isdir(d):
                log.debug("Creating output directory %s", d)
                os.makedirs(d)

    def check_directory(self, call: tuple[T_Source_contra, T_Data]) -> None:
        """Check if directory is missing, and create it if necessary."""
        self.check_directories([call])

    def check_overwriting_calls(
        self, calls: Sequence[tuple[T_Source_contra, T_Data]]
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
        self, call: tuple[T_Source_contra, T_Data], **kwargs: Any
    ) -> Any:
        """Execute a single call.

        :Not implemented: implement in a module subclass.

        Parameters
        ----------
        kwargs
            Passed to the writing function.
        """
        raise NotImplementedError("Implement in a module subclass.")

    def send_calls(
        self, calls: Sequence[tuple[T_Source_contra, T_Data]], **kwargs: Any
    ) -> list[Any]:
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


T = TypeVar("T", covariant=True)


@runtime_checkable
class Splitable(Protocol[T]):
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
    def unfixed(self) -> Iterable[T]:
        """Iterable of parameters that are not fixed.

        This must take into account the values that are specified (or not) in the
        data-manager parameters.
        """

    def get_filename(self, **fixes: Any) -> T:
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

    def get_filename(self, **kwargs: Any) -> T_Source:
        """Return a filename corresponding to current parameters and kwargs."""
        return self.source.get_filename(**kwargs)
