import os
import subprocess
import sys
import msvcrt
import _subprocess
import time

# Create pipe for communication
pipeout, pipein = os.pipe()

# Prepare to pass to child process
curproc = _subprocess.GetCurrentProcess()
pipeouth = msvcrt.get_osfhandle(pipeout)
pipeoutih = _subprocess.DuplicateHandle(
    curproc,
    pipeouth,
    curproc,
    0,
    0,
    _subprocess.DUPLICATE_SAME_ACCESS)

pipearg = str(int(pipeoutih))

# Start child with argument indicating which FD/FH to read from
subproc = subprocess.Popen(['python', 'child.py', str(os.getpid()), pipearg], close_fds=True)

# Write to child (could be done with os.write, without os.fdopen)
pipefh = os.fdopen(pipein, 'w')
pipefh.write("Hello from parent.")
pipefh.close()


# Close read end of pipe in parent
os.close(pipeout)
time.sleep(3)
pipeoutih.Close()

# Wait for the child to finish
subproc.wait()