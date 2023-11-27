from collections.abc import Hashable, Iterable, Mapping, Sequence
from typing import Any

from .file_manager import FileManager
from .loader import LoaderAbstract
from .writer import WriterAbstract


class DatasetAbstract:
    SHORTNAME: str | None = None
    """Short name to refer to this dataset class."""
    ID: str | None = None
    """Long name to identify uniquely this dataset class."""

    PARAMS_NAMES: Sequence[Hashable] = []
    """List of parameters names."""
    PARAMS_DEFAULTS: dict = {}
    """Default values of parameters.

    Optional. Can be used to define default values for parameters local to a
    dataset, (*ie* that are not defined in project-wide
    :class:`ParametersManager`).
    """

    def __init__(
        self,
        params: Mapping[str, Any] | None = None,
        exact_params: bool = False,
        **kwargs,
    ):
        self.exact_params: bool = exact_params

        self.file_manager: FileManager | None = None
        self.loader: LoaderAbstract | None = None
        self.writer: WriterAbstract | None = None

        self.params: dict[str, Any]
        """Mapping of parameters values."""
        self.allowed_params = set(self.PARAMS_NAMES)
        """Mutable copy of the list of allowed parameters.

        We may add to it from parameters found in the filename structure.
        """

        # Set parameters
        self.set_params(params, **kwargs)

        # Now we can initialize modules
        self.file_manager = FileManager(self)


    def __str__(self) -> str:
        name = []
        if self.SHORTNAME is not None:
            name.append(self.SHORTNAME)
        if self.ID is not None:
            name.append(self.ID)

        clsname = self.__class__.__name__
        if name:
            clsname = f' ({clsname})'

        return ':'.join(name) + clsname

    def __repr__(self) -> str:
        s = []
        s.append(self.__str__())
        s.append('Parameters:')
        s.append(f'\tdefined: {self.PARAMS_NAMES}')
        if self.PARAMS_DEFAULTS:
            s.append(f'\tdefaults: {self.PARAMS_DEFAULTS}')
        s.append(f'\tallowed: {self.allowed_params}')
        s.append(f'\tset: {self.params}')

        if self.file_manager is not None:
            s += str(self.file_manager).splitlines()

        return '\n'.join(s)

    def set_params(self, params: Mapping[str, Any] | None = None, **kwargs):
        """Set parameters values.

        Parameters
        ----------
        params:
            Mapping of parameters values.
        kwargs:
            Parameters values. Will take precedence over ``params``.
            Parameters will be taken in order of first available in:
            ``kwargs``, ``params``, :attr:`PARAMS_DEFAULTS`.
        """
        if params is None:
            params = {}
        params = dict(params)  # shallow copy
        params = params | self.PARAMS_DEFAULTS
        params.update(kwargs)

        self.params = params
        self._reset_cached_properties()
        self._check_param_known(params)

    def _check_param_known(self, params: Iterable[str]):
        """Check if the parameters are known to this dataset class.

        A 'known parameter' is one present in :attr:`PARAMS_NAMES` or defined
        in the filename pattern (as a varying group).

        Only run the check if :attr:`exact_params` is True.
        """
        if not self.exact_params:
            return
        for p in params:
            if p not in self.allowed_params:
                raise KeyError(f"Parameter '{p}' was not expected for dataset {self}")

    def _reset_cached_properties(self) -> None:
        if self.file_manager is not None:
            self.file_manager._reset_cached_properties()
        # do this for others
