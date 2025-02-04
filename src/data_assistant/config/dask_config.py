"""Dask management."""

from __future__ import annotations

import logging
import sys
import typing as t
from collections.abc import Sequence

import distributed
from distributed.deploy.cluster import Cluster
from distributed.scheduler import Scheduler
from distributed.security import Security
from distributed.worker import Worker
from traitlets import (
    Bool,
    Dict,
    Enum,
    Float,
    Instance,
    Int,
    List,
    Type,
    Unicode,
    Union,
)
from traitlets.utils.importstring import import_item

from .section import Section, subsection
from .util import tag_all_traits

log = logging.getLogger(__name__)


class DaskClusterAbstract(Section):
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
        args = self.trait_values(cluster_args=True)
        for name in self.trait_names(cluster_kwargs=True):
            kwargs = args.pop(name)
            args.update(kwargs)
        return args


@tag_all_traits(cluster_args=True)
class DaskLocalCluster(DaskClusterAbstract):
    cluster_class = distributed.LocalCluster

    n_workers = Int(None, allow_none=True, help="Number of workers to start.")

    memory_limit = Union(
        [Unicode(), Float(), Int()],
        default_value="auto",
        allow_none=True,
        help="""\
        Sets the memory limit *per worker*.

        Notes regarding argument data type:

        * If None or 0, no limit is applied.
        * If "auto", the total system memory is split evenly between the workers.
        * If a float, that fraction of the system memory is used *per worker*.
        * If a string giving a number of bytes (like ``"1GiB"``),
          that amount is used *per worker*.
        * If an int, that number of bytes is used *per worker*.

        Note that the limit will only be enforced when ``processes=True``, and the
        limit is only enforced on a best-effort basis — it's still possible for
        workers to exceed this limit.""",
    )

    processes = Bool(
        None,
        allow_none=True,
        help=(
            "Whether to use processes (True) or threads (False). "
            "Defaults to True, unless ``worker_class=Worker``, "
            "in which case it defaults to False."
        ),
    )

    threads_per_worker = Int(
        None, allow_none=True, help=("Number of threads per each worker.")
    )

    scheduler_port = Int(
        0,
        help=(
            "Port of the scheduler. Use 0 to choose a random port (default). "
            "8786 is a common choice."
        ),
    )

    silence_logs = Union(
        [Int(), Bool()],
        default_value=logging.WARN,
        allow_none=True,
        help=(
            "Level of logs to print out to stdout. ``logging.WARN`` by default."
            "Use a falsey value like False or None for no change."
        ),
    )

    host = Unicode(
        None,
        allow_none=True,
        help=(
            "Host address on which the scheduler will listen, "
            "defaults to only localhost."
        ),
    )

    dashboard_address = Unicode(
        ":8787",
        allow_none=True,
        help=(
            "Address on which to listen for the Bokeh diagnostics server like "
            "``localhost:8787`` or ``0.0.0.0:8787``. Defaults to ``:8787``. "
            "Set to ``None`` to disable the dashboard. "
            "Use ``:0`` for a random port."
        ),
    )

    worker_dashboard_address = Unicode(
        None,
        allow_none=True,
        help=(
            "Address on which to listen for the Bokeh worker diagnostics server like "
            "``localhost:8787`` or ``0.0.0.0:8787``. Defaults to None which disables "
            "the dashboard. Use ``:0`` for a random port."
        ),
    )

    asynchronous = Bool(
        False,
        help=(
            "Set to True if using this cluster within async/await functions or within"
            "Tornado gen.coroutines.  This should remain False for normal use."
        ),
    )

    blocked_handlers = List(
        Unicode(),
        default_value=None,
        allow_none=True,
        help=(
            "A list of strings specifying a blocklist of handlers to disallow on the "
            "Scheduler, like ``['feed', 'run_function']``"
        ),
    )

    service_kwargs = Dict(
        key_trait=Unicode(),
        default_value=None,
        allow_none=True,
        help="Extra keywords to hand to the running services.",
    )

    security = Union(
        [Instance(klass=Security), Bool()],
        default_value=None,
        allow_none=True,
        help=(
            "Configures communication security in this cluster. Can be a security "
            "object, or True. If True, temporary self-signed credentials will "
            "be created automatically."
        ),
    )

    protocol = Unicode(
        None,
        allow_none=True,
        help=(
            "Protocol to use like ``tcp://``, ``tls://``, ``inproc://``. "
            "This defaults to sensible choice given other keyword arguments like "
            "``processes`` and ``security``."
        ),
    )

    interface = Unicode(
        None,
        allow_none=True,
        help="Network interface to use.  Defaults to lo/localhost.",
    )

    worker_class = Type(
        klass=Worker,
        default_value=None,
        allow_none=True,
        help=(
            "Worker class used to instantiate workers from. Defaults to ``Worker`` if "
            "``processes=False`` and Nanny if ``processes=True`` or omitted."
        ),
    )

    worker_kwargs = Dict(
        default_value={},
        help=(
            "Extra worker arguments. Any additional keyword arguments will be passed "
            "to the ``Worker`` class constructor."
        ),
    ).tag(cluster_kwargs=True)


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
            "can pass it through the ``scheduler_options`` argument "
            "``interface=your_worker_interface, scheduler_options={'interface': "
            "your_scheduler_interface}``."
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

    worker_extra_args = List(
        Unicode(),
        default_value=[],
        help="Additional arguments to pass to dask-worker.",
    )

    job_script_prologue = List(
        Unicode(),
        default_value=[],
        help="Other commands to add to script before launching worker.",
    )

    job_directives_skip = List(
        Unicode(),
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

    scheduler_options = Dict(
        key_trait=Unicode(),
        default_value=None,
        allow_none=True,
        help=(
            "Used to pass additional arguments to Dask Scheduler. For example use "
            "``scheduler_options={'dashboard_address': ':12435'}`` to specify which "
            "port the web dashboard should use or "
            "``scheduler_options={'host': 'your-host'}`` to specify the host the "
            "Dask scheduler should run on. "
            "See :class:`distributed.Scheduler` for more details."
        ),
    )

    scheduler_cls = Type(
        klass=Scheduler,
        help=(
            "Changes the class of the used Dask Scheduler. Defaults to  Dask's "
            ":class:`distributed.Scheduler`."
        ),
    )

    shared_temp_directory = Unicode(
        None,
        allow_none=True,
        help=(
            "Shared directory between scheduler and worker (used for example by temporary"
            "security certificates) defaults to current working directory if not set."
        ),
    )

    wait_worker_timeout = Float(
        None,
        allow_none=True,
        help=(
            "Number of seconds to wait for workers before "
            "raising dask.distributed.TimeoutError "
        ),
    ).tag(cluster_args=False)


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
        Unicode(),
        help=(
            "List of other PBS options. "
            "Each option will be prepended with the #PBS prefix."
        ),
    )


@tag_all_traits(cluster_args=True)
class DaskClusterSLURM(DaskClusterJobQueue):
    """Config for SLURM Cluster.

    I deviate from documented parameters of :class:`dask_jobqueue.slurm.SLURMJob` that
    do not seem to be correct (`job_cpu` is not used it seems to me?).

    The traits :attr:`workers_per_job`, :attr:`threads_per_job` and
    :attr:`mem_per_worker` will be used to obtain necessary parameters (
    :attr:`~DaskClusterJobQueue.cores`, :attr:`~DaskClusterJobQueue.processes`
    and :attr:`~DaskClusterJobQueue.memory`).
    """

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

    job_extra_directives = List(
        Unicode(),
        default_value=[],
        help=(
            "List of other PBS options. "
            "Each option will be prepended with the #PBS prefix."
        ),
    )

    workers_per_job = Int(1, help="Number of workers per job").tag(cluster_args=False)

    threads_per_job = Int(1, help="Number of threads per job").tag(cluster_args=False)

    mem_per_worker = Int(4, help="Number memory in GiB per worker").tag(
        cluster_args=False
    )

    def get_cluster_kwargs(self) -> dict:
        """Return cluster keyword arguments.

        Uses :attr:`workers_per_job`, :attr:`threads_per_job` and :attr:`mem_per_worker`
        to obtain necessary arguments.
        """
        kwargs = super().get_cluster_kwargs()

        kwargs["cores"] = self.threads_per_job * self.workers_per_job
        kwargs["processes"] = self.workers_per_job
        kwargs["memory"] = f"{self.workers_per_job * self.mem_per_worker}GiB"

        return kwargs


DEFAULT_CLUSTER_NAMES = {
    "local": DaskLocalCluster,
    "pbs": DaskClusterPBS,
    "slurm": DaskClusterSLURM,
}


class DaskConfig(Section):
    """Section for Dask management."""

    cluster_names: dict[str, type[DaskClusterAbstract]] = DEFAULT_CLUSTER_NAMES

    # cannot be changed from a subclass
    selected_clusters: list[str] = list(DEFAULT_CLUSTER_NAMES.keys())

    cluster_type = Enum(
        list(DEFAULT_CLUSTER_NAMES.keys()),
        default_value="slurm",
        help="Cluster type to use.",
    )

    cluster: Cluster

    @classmethod
    def _setup_section(cls):
        """Set up the class after definition.

        Only add the subsections corresponding to the ``selected_clusters`` attribute.
        """
        # Add selected cluster types
        for name in cls.selected_clusters:
            setattr(cls, name, subsection(cls.cluster_names[name]))

        super()._setup_section()

        # Setup cluster_type default values
        cls.cluster_type.values = cls.selected_clusters
        cls.cluster_type.default_value = cls.selected_clusters[0]

    @classmethod
    def set_selected_clusters(cls, select: Sequence[str]):
        """Change the selected clusters types.

        Only those selected will be available to configure as subsections.
        """
        # Remove all DaskClusterAbstract attributes
        for name in cls.selected_clusters:
            delattr(cls, name)
        cls.selected_clusters = list(select)
        cls._setup_section()

    @property
    def cluster_section(self) -> DaskClusterAbstract:
        """Configuration section for current cluster type."""
        return getattr(self, self.cluster_type)

    def start(self, **kwargs: t.Any):
        """Start Dask distributed client.

        This method instanciates a subclass of :class:`DaskClusterAbstract` in
        ``self.dask``, which will start the Cluster specified by
        :attr:`DaskClusterAbstract.cluster_class` and the associated
        :class:`distributed.Client`. Both are accessible as attributes
        :attr:`dask.client` and :attr:`dask.cluster`

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
        self.cluster = self.cluster_section.get_cluster(**kwargs)
        """Dask cluster object, local or distributed via jobqueue."""

        self.client = distributed.Client(self.cluster)
        """Dask client object."""

    def wait_for_workers(self, wait: int):
        """Wait for workers (if cluster is not local)."""
        if not isinstance(self.cluster_section, DaskClusterJobQueue):
            return

        log.info("Waiting for %d worker(s)", wait)
        self.client.wait_for_workers(
            n_workers=wait, timeout=self.cluster_section.wait_worker_timeout
        )

    def scale(self, wait: int | None = None, **kwargs):
        """Scale cluster workers.

        If the cluster is local, do nothing.

        Parameters
        ----------
        wait
            If is an int, wait for that many workers. Timeout is given by the trait
            :attr:`.DaskClusterJobQueue.wait_worker_timeout`.
        kwargs
            Arguments passed to ``cluster.scale()``. See the documentation for your
            specific cluster type to see the parameters available.
        """
        if not isinstance(self.cluster_section, DaskClusterJobQueue):
            return

        log.info("Scale cluster to: %s", repr(kwargs))
        self.cluster.scale(**kwargs)

        if wait is not None:
            self.wait_for_workers(wait)

    def adapt(self, wait: int | None = None, **kwargs):
        """Adapt cluster workers.

        Parameters
        ----------
        wait
            If is an int, wait for that many workers. Timeout is given by the trait
            :attr:`.DaskClusterJobQueue.wait_worker_timeout`.
        kwargs
            Arguments passed to ``cluster.adapt()``. See the documentation for your
            specific cluster type to see the parameters available.
        """
        if not isinstance(self.cluster_section, DaskClusterJobQueue):
            return

        log.info("Set cluster to adapt (%s)", repr(kwargs))
        self.cluster.adapt(**kwargs)

        if wait is not None:
            self.wait_for_workers(wait)
