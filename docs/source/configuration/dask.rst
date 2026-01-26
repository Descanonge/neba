
******************
Dask configuration
******************

Selecting cluster type
======================

Add :class:`.DaskConfig` as a subsection to your application. It will provide
configuration for all types of clusters (local, PBS, SLURM, etc). You may only
use some of these clusters in your project. To avoid having cluttering
parameters you can list the clusters you need with
:attr:`.DaskConfig.set_selected_clusters`::

    from data_assistant.config.dask_config import DaskConfig
    from data_assistant.config import Subsection

    DaskConfig.set_selected_clusters(["local", "slurm"])

    class App(ApplicationBase):
        dask = Subsection(DaskConfig)


Here are the available clusters and their names:

+---------+-------------------------------+--------------------------------------+
| Name    | Configuration section         | Cluster class                        |
+---------+-------------------------------+--------------------------------------+
| local   | :class:`.DaskLocalCluster`    |  :class:`distributed.LocalCluster`   |
+---------+-------------------------------+--------------------------------------+
| pbs     | :class:`.DaskClusterJobQueue` | :class:`dask_jobqueue.PBSCluster`    |
|         | + :class:`.DaskClusterPBS`    |                                      |
+---------+-------------------------------+--------------------------------------+
| slurm   |  :class:`.DaskClusterJobQueue`| :class:`dask_jobqueue.SLURMCluster`  |
|         |  + :class:`.DaskClusterSLURM` |                                      |
+---------+-------------------------------+--------------------------------------+

Cluster parameters will be available in a subsection corresponding to their
name, for instance with the example above ``dask.local.n_workers=4``,
``dask.slurm.n_workers=8``.

You can then select the cluster you want to use in your script with the trait
:attr:`dask.cluster_type<.DaskConfig.cluster_type>`, for instance using the
command line: ``--dask.cluster_type=local``.

Using cluster
=============

The ``dask`` subsection offers various methods to help you setup your cluster.

The cluster is started using :meth:`~.DaskConfig.start`. This will start a
cluster according to the parameters in the corresponding section. You can pass
keyword arguments to overwrite some parameters::

    """Your config file (TOML)
    dask.slurm.n_workers = 6
    dask.slurm.memory = "8GB"
    ...
    dask.cluster_type = "slurm"
    """

    app.dask.start(n_workers=12)


This will store the cluster and client objects in ``dask.cluster`` and
``dask.client``.

The cluster can be :meth:`scaled<.DaskConfig.scale>`, or set to
:meth:`adapt<.DaskConfig.adapt>`. If your cluster type is set to local, this has
no effect::

    app.dask.adapt(minimum_workers=2, maximum_workers=6)

    # This will automatically wait for 2 workers before continuing
    app.dask.scale(n_workers=12, wait=2)

To change the scaling via parameters rather than having to change your script
you can use the :class:`dask.deploy<.DaskConfig._deploySectionDef>` section. It
currently only supports scaling the number of workers. Call the section to
start scaling/adapting. The arguments you give to the call are default values
that may be overwritten by parameters::

    app.dask.start()
    app.dask.deploy(mode="scaling", n_workers=4)

    # Parameters: --dask.deploy.n_workers=8
