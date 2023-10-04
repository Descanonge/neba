"""Dask management.
"""
from typing import Any

import distributed
import dask_jobqueue as djq

from traitlets import Bool, Enum, Float, Int, List, Unicode
from traitlets.config import Application

from .core import AutoConfigurable

class DaskLocalCluster(AutoConfigurable):
    pass

# classes that reproduce jobqueue config (and nothing more)
class DaskJobQueueCluster(AutoConfigurable):

    # Job specific parameters
    cores = Int(help='Total number of cores per job.')
    memory = Int(help='Total amount of memory per job.')

    processes = Int(None, allow_none=True,
        help=('Cut the job up into this many processes. '
              'Good for GIL workloads or for nodes with many cores. '
              'By default, process ~= sqrt(cores) so that the number of '
              'processes and the number of threads per process is roughly the same.'))

    interface = Unicode(None, allow_none=True,
        help=("Network interface like 'eth0' or 'ib0'. This will be used both "
              'for the Dask scheduler and the Dask workers interface. '
              'If you need a different interface for the Dask scheduler you '
              'can pass it through the scheduler_options argument: '
              "interface=your_worker_interface, scheduler_options={'interface': "
              'your_scheduler_interface}.'))

    nanny = Bool(help='Whether or not to start a nanny process')

    local_directory = Unicode(
        None, allow_none=True,
        help='Dask worker local directory for file spilling.')

    death_timeout = Float(
        None, allow_none=True,
        help='Seconds to wait for a scheduler before closing workers.')

    job_directives_skip = List(
        Unicode,
        help=('Directives to skip in the generated job script header. '
              'Directives lines containing the specified strings will be removed. '
              'Directives added by job_extra_directives won’t be affected.'))

    log_directory = Unicode(help='Directory to use for job scheduler logs.')

    shebang = Unicode(
        help='Path to desired interpreter for your batch submission script.')

    python = Unicode(
        help=('Python executable used to launch Dask workers. '
              'Defaults to the Python that is submitting these jobs.'))

    name = Unicode('dask-worker', help='Name of Dask worker.')

    # Cluster related parameters
    n_workers = Int(0, help='Number of workers to start by default.')

    silence_logs = Unicode(
        help=('Log level like "debug", "info", or "error" to emit here '
              'if the scheduler is started locally.'))

    asynchronous = Bool(
        help='Whether or not to run this cluster object with the async/await syntax.')

class DaskClusterPBS(DaskJobQueueCluster):
    cluster_class = djq.PBSCluster

    queue = Unicode(
        help='Destination queue for each worker job. Passed to `#PBS -q` option.')

    account = Unicode(
        help=('Accounting string associated with each worker job. '
              'Passed to `#PBS -A` option.'))

    resource_spec = Unicode(
        help='Request resources and specify job placement. Passed to `#PBS -l` option.')

    walltime = Unicode(
        help='Walltime for each worker job.')

    job_extra_directives = List(
        Unicode,
        help=('List of other PBS options. '
              'Each option will be prepended with the #PBS prefix.'))

class DaskClusterSLURM(DaskJobQueueCluster):
    cluster_class = djq.SLURMCluster

    queue = Unicode(
        help='Destination queue for each worker job. Passed to `#SBATCH -p` option.')

    account = Unicode(
        help=('Accounting string associated with each worker job. '
              'Passed to `#PBS -A` option.'))

    walltime = Unicode(
        help='Walltime for each worker job.')

    job_cpu = Int(
        help=('Number of cpu to book in SLURM, if None, defaults to worker '
              '`threads * processes`'))

    job_mem = Unicode(
        help=('Amount of memory to request in SLURM. If None, defaults '
              'to worker processes * memory'))

    job_extra_directives = List(
        Unicode,
        help=('List of other PBS options. '
              'Each option will be prepended with the #PBS prefix.'))


CLUSTER_CONF_CLASSES = {
    'PBS': DaskClusterPBS,
    'SLURM': DaskClusterSLURM
}


class DaskCluster(AutoConfigurable):

    cluster_type = Enum(CLUSTER_CONF_CLASSES.keys(), default_value='SLURM',
                        help='Type of cluster to use.')

    # maybe more personnal parameters to setup cluster
    # (like total memory, or per jobs)
    # maybe use different classes depending on how user want to work

    def start(self):
        """Start a cluster and client."""
        self.cluster_conf = CLUSTER_CONF_CLASSES[self.cluster_type](parent=self)
        cluster_cls = self.cluster_conf.cluster_class
        self.cluster_kwargs = self.cluster_conf.trait_values().copy()

        self.cluster = cluster_cls(**self.cluster_kwargs)
        self.client = distributed.Client(self.cluster)


class DaskApp(Application):
    """Application class for Dask management."""

    listed_cluster_types = ['PBS', 'SLURM']

    # add 'local' cluster ? or other ways to start dask ?

    def __init_subclass__(cls, /, **kwargs):
        """Subclass init hook."""
        cls.classes.append(DaskCluster)
        for c in cls.listed_cluster_types:
            cls.classes.append(CLUSTER_CONF_CLASSES[c])

        super().__init_subclass__(**kwargs)

    def start_dask(self, **kwargs: Any):
        """Start Dask distributed client.

        This method instanciates a :class:`DaskCluster` in ``self.dask``, which
        will start the Cluster specified by :attr:`DaskCluster.cluster_type` and
        the associated :class:`distributed.Client`. Both are accessible as
        ``self.dask.client`` and ``self.dask.cluster``.

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
        self.dask = DaskCluster(parent=self, **kwargs)
        self.dask.start()
        self.log.info('Dashboard available at %s', self.dask.client.dashboard_link)
