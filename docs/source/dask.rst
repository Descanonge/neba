
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
