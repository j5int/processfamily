import os
import subprocess
import msvcrt
import win32api

# Create pipe for communication
pipeout, pipein = os.pipe()

# Prepare to pass to child process
curproc = win32api.GetCurrentProcess()
pipeouth = msvcrt.get_osfhandle(pipeout)

# Start child with argument indicating which FD/FH to read from
subproc = subprocess.Popen(['python', 'child.py', str(os.getpid()), str(int(pipeouth))], close_fds=True)

# Write to child (could be done with os.write, without os.fdopen)
pipefh = os.fdopen(pipein, 'w')
pipefh.write("Hello from parent.")
pipefh.close()

# Wait for the child to finish
subproc.wait()