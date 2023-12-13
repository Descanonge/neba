"""Dask management."""

from __future__ import annotations

import sys
from typing import Any

import distributed
from distributed.deploy.cluster import Cluster
from distributed.security import Security
from traitlets import Bool, Enum, Float, Instance, Int, List, Unicode, Union
from traitlets.utils.importstring import import_item

from .scheme import Scheme
from .util import tag_all_traits


class DaskClusterAbstract(Scheme):
    cluster_class: type[Cluster] | str

    @classmethod
    def get_cluster_class(cls) -> type[Cluster]:
        if isinstance(cls.cluster_class, str):
            return import_item(cls.cluster_class)
        return cls.cluster_class

    def get_cluster(self, **kwargs) -> Cluster:
        """Start new cluster.

        Parameters
        ----------
        kwargs:
            Override arguments set by configuration.
        """
        config = self.get_cluster_kwargs()
        config.update(kwargs)
        cluster = self.get_cluster_class()(**config)
        return cluster

    def get_cluster_kwargs(self) -> dict:
        """Return cluster __init__ keyword arguments from configuration."""
        return self.trait_values(cluster_args=True)


@tag_all_traits(cluster_args=True)
class DaskLocalCluster(DaskClusterAbstract):
    cluster_class = distributed.LocalCluster


@tag_all_traits(cluster_args=True)
class DaskClusterJobQueue(DaskClusterAbstract):
    # Job specific parameters
    cores = Int(help="Total number of cores per job.")
    memory = Unicode(help="Total amount of memory per job.")

    processes = Int(
        None,
        allow_none=True,
        help=(
            "Cut the job up into this many processes. "
            "Good for GIL workloads or for nodes with many cores. "
            "By default, process ~= sqrt(cores) so that the number of "
            "processes and the number of threads per process is roughly the same."
        ),
    )

    interface = Unicode(
        None,
        allow_none=True,
        help=(
            "Network interface like 'eth0' or 'ib0'. This will be used both "
            "for the Dask scheduler and the Dask workers interface. "
            "If you need a different interface for the Dask scheduler you "
            "can pass it through the scheduler_options argument: "
            "interface=your_worker_interface, scheduler_options={'interface': "
            "your_scheduler_interface}."
        ),
    )

    nanny = Bool(help="Whether or not to start a nanny process")

    local_directory = Unicode(
        None, allow_none=True, help="Dask worker local directory for file spilling."
    )

    death_timeout = Float(
        None,
        allow_none=True,
        help="Seconds to wait for a scheduler before closing workers.",
    )

    worker_command = List(
        Unicode,  # type: ignore
        default_value=["distributed.cli.dask_worker"],
        help="Command to run when launching a worker.",
    )

    worker_extra_args = List(
        Unicode,  # type: ignore
        default_value=[],
        help="Additional arguments to pass to dask-worker.",
    )

    job_script_prologue = List(
        Unicode,  # type: ignore
        default_value=[],
        help="Other commands to add to script before launching worker.",
    )

    job_directives_skip = List(
        Unicode,  # type: ignore
        default_value=[],
        help=(
            "Directives to skip in the generated job script header. "
            "Directives lines containing the specified strings will be removed. "
            "Directives added by job_extra_directives won’t be affected."
        ),
    )

    log_directory = Unicode(
        None, allow_none=True, help="Directory to use for job scheduler logs."
    )

    shebang = Unicode(
        None,
        allow_none=True,
        help="Path to desired interpreter for your batch submission script.",
    )

    python = Unicode(
        sys.executable,
        help=(
            "Python executable used to launch Dask workers. "
            "Defaults to the Python that is submitting these jobs."
        ),
    )

    name = Unicode(
        None,
        allow_none=True,
        help="Name of Dask worker. This is typically set by the Cluster.",
    )

    # Cluster related parameters
    n_workers = Int(0, help="Number of workers to start by default.")

    silence_logs = Unicode(
        "error",
        help=(
            'Log level like "debug", "info", or "error" to emit here '
            "if the scheduler is started locally."
        ),
    )

    asynchronous = Bool(
        False,
        help="Whether or not to run this cluster object with the async/await syntax.",
    )

    security = Union(
        [Instance(klass=Security), Bool()],
        default_value=None,
        allow_none=True,
        help=(
            "A dask.distributed security object if you're using TLS/SSL. "
            "If True, temporary self-signed credentials will be created automatically."
        ),
    )

    # Still some missing


@tag_all_traits(cluster_args=True)
class DaskClusterPBS(DaskClusterJobQueue):
    cluster_class = "dask_jobqueue.PBSCluster"

    queue = Unicode(
        help="Destination queue for each worker job. Passed to `#PBS -q` option."
    )

    account = Unicode(
        help=(
            "Accounting string associated with each worker job. "
            "Passed to `#PBS -A` option."
        )
    )

    resource_spec = Unicode(
        help="Request resources and specify job placement. Passed to `#PBS -l` option."
    )

    walltime = Unicode(help="Walltime for each worker job.")

    job_extra_directives = List(
        Unicode,  # type: ignore
        help=(
            "List of other PBS options. "
            "Each option will be prepended with the #PBS prefix."
        ),
    )


@tag_all_traits(cluster_args=True)
class DaskClusterSLURM(DaskClusterJobQueue):
    cluster_class = "dask_jobqueue.SLURMCluster"

    queue = Unicode(
        None,
        allow_none=True,
        help="Destination queue for each worker job. Passed to `#SBATCH -p` option.",
    )

    account = Unicode(
        None,
        allow_none=True,
        help=(
            "Accounting string associated with each worker job. "
            "Passed to `#PBS -A` option."
        ),
    )

    walltime = Unicode(None, allow_none=True, help="Walltime for each worker job.")

    job_cpu = Int(
        help=(
            "Number of cpu to book in SLURM, if None, defaults to worker "
            "`threads * processes`"
        )
    )

    job_mem = Unicode(
        help=(
            "Amount of memory to request in SLURM. If None, defaults "
            "to worker processes * memory"
        )
    )

    job_extra_directives = List(
        Unicode,  # type: ignore
        default_value=[],
        help=(
            "List of other PBS options. "
            "Each option will be prepended with the #PBS prefix."
        ),
    )


DEFAULT_CLUSTER_NAMES = {
    "local": DaskLocalCluster,
    "pbs": DaskClusterPBS,
    "slurm": DaskClusterSLURM,
}


class DaskConfig(Scheme):
    """Scheme for Dask management."""

    cluster_names: dict[str, type[DaskClusterAbstract]] = DEFAULT_CLUSTER_NAMES

    # cannot be changed from a subclass
    selected_clusters: list[str] = list(DEFAULT_CLUSTER_NAMES.keys())

    cluster_type = Enum(list(DEFAULT_CLUSTER_NAMES.keys()), default_value="slurm")

    @classmethod
    def _setup_scheme(cls):
        # Add selected cluster types
        for name in cls.selected_clusters:
            setattr(cls, name, cls.cluster_names[name])

        super()._setup_scheme()

        # Setup cluster_type default values
        cls.cluster_type.values = cls.selected_clusters
        cls.cluster_type.default_value = cls.selected_clusters[0]

    @classmethod
    def set_selected_clusters(cls, select):
        # Remove all DaskClusterAbstract attributes
        for name in cls.selected_clusters:
            delattr(cls, name)
        cls.selected_clusters = select
        cls._setup_scheme()

    def start_dask(self, **kwargs: Any):
        """Start Dask distributed client.

        This method instanciates a :class:`DaskCluster` in ``self.dask``, which
        will start the Cluster specified by :attr:`DaskCluster.cluster_type` and
        the associated :class:`distributed.Client`. Both are accessible as
        attributes :attr:`dask.client` and :attr:`dask.cluster`

        The cluster can either be a :class:`LocalCluster` or one of the clusters
        supported by :mod:`dask-jobqueue`. The cluster is instanciated with the
        parameters specified in the configuration, and can be overriden by
        ``kwargs``.

        Parameters
        ----------
        kwargs:
            Arguments passed to the Cluster initialization. They will override
            the current configuration.
        """
        cluster_cls = self.cluster_names[self.cluster_type]
        self.cluster = cluster_cls().get_cluster(**kwargs)

        self.client = distributed.Client(self.cluster)
        # self.log.info('Dashboard available at %s', self.dask.client.dashboard_link)
