"""Dask management.

Things to remember:
howto chunk ?
- small enough that many of them fit in memory
- big enough so that the computation of one task (= one python function call)
  is significantly longer than the overhead of that task (1ms), to be worth it.
- If data is read or written on disk, it should align with how the data is
  stored. You want to avoid having to repeatedly read plenty of file.
  Having arrays chunks that are multiple of those on disk is okay though.

Below 1MB is generally not good. Between 100MB and 1GB is good, depending on the
resources available. Above 1GB is for less common use cases (either because
the dataset is very large and/or you have a lot of memory per core).

For a single precision float (32bits),
- a 2D array of shape (2000, 2000) represents 15MB
- a 3D array of shape (20, 400, 400) represents 12MB

When I said 'small enough that many of them fit in memory': this includes
all variables used for the present task and the result, as well as potential
copies made by the underlying functions.
And by 'many of them', this depends on the number of threads available to the
worker. So scale the number of threads per worker with the memory per core
(which will be *split* across threads).

Then come the distinction between threads and processes. The dask scheduler
(which supervise the different workers) can be set to use a single process with
multiple threads. In this case each worker has one thread.

This is fine on local machines with 4 or 8 cores, but on HPC clusters where
there is many cores and a lot of memory you can up the number of threads. At
this point it is beneficial to split all those threads between multiple
processes. Then each worker is on one process, running on one CPU core, and has
a pool of threads to use.
The distributed scheduler is recommended, and has plenty of additionnal features
that are welcome.

Remember:
- if your computation release the GIL (like functions from numpy, scipy, pandas),
  you can parallelize just with threads. Prefer then having multiple threads,
  in the limit of (memory) ressources of course.
- if not, use multiple processes to parallelize. This has the disavantage of
  having to move data to each process (located on a different cpu core, hence
  moving data around). Whereas threads are on the same core, and share the
  memory.

You are probably in the first case, having to deal with a big dataset on disk
and a collection of numpy functions that acts on the whole dataset. You want
out-of-core computation and maybe parallelization.
Favor threads, maybe split in a few processes (avoid more than ~20 threads per
worker), because Dask will be able to run the same numpy function on different
chunks at the same time (because numpy functions release the GIL).

Maybe save your data with Zarr. Netcdf files can be read from in parallel, but
not written. Zarr can do both easily, but is less standard in geosciences than
netcdf or hdf.

howto Access the dashboard

Setup Dask Client.
The Client is the user-facing object that you will interact with to work with
Dask. It contains the scheduler, and it is created from a Cluster object.
This can be a LocalCluster (the default) if you work on a single machine, or a
more evolved object that can deal with HPC clusters of distributed machines.
We will setup the later.

Okayyyy what do we need ?
Project wide defaults, appropriate for clusters.
That can be overriden easily for specific scripts. Ça parait parfait pour notre
gestionnaire de paramètres ?
"""
import distributed
import dask_jobqueue as djq

from traitlets import Bool, Enum, Float, Int, List, Unicode

from .core import ConfigurablePlus

CLUSTER_TYPES = {
    'PBS': djq.PBSCluster,
    'SLURM': djq.SLURMCluster,
}

class DaskClusterConfig(ConfigurablePlus):

    cluster_type = Enum(CLUSTER_TYPES.keys(), default_value='SLURM',
                        help='Type of cluster to use.')

    # maybe more personnal parameters to setup cluster
    # (like total memory, or per jobs)
    # maybe use different classes depending on how user want to work

    def start(self) -> tuple[distributed.Client,
                             distributed.deploy.Cluster]:
        params = self.config  # FIXME
        cluster = CLUSTER_TYPES[params.cluster_type](**params)
        client = distributed.Client(cluster)
        return client, cluster


# classes that reproduce jobqueue config (and nothing more)
class DaskJobQueueCluster(ConfigurablePlus):

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
