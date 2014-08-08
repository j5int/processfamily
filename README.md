processfamily
=============

A library for launching, maintaining, and terminating a family of long-lived python child processes on Windows and *nix.

The child processes can be launched from a console application or a Windows service / *nix daemon.
A simple line-oriented text-based control protocol is implemented over stdin / stdout that allows the child process to be cleanly shutdown.
(This implies that the children should not be using stdin / stdout for other purposes.)

In order to avoid orphaned processes, the child processes are created in a way that will ensure that they are killed if the parent dies.
On Windows this is implemented using a shared [Job Object](http://msdn.microsoft.com/en-us/library/ms684161(v=vs.85).aspx).
If the parent process is not already in a Job, it will create a Job Object, and add itself in to that job before any of the child processes are created.
For *nix this uses prctl PR_SET_PDEATHSIG setting.

