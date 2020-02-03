from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import *
import os
import subprocess
import msvcrt
import sys

# Create pipe for communication
pipeout, pipein = os.pipe()
pipe2out, pipe2in = os.pipe()

# Start child with argument indicating which FD/FH to read from
subproc = subprocess.Popen([
       sys.executable,
       'child.py',
       str(os.getpid()),
       str(int(msvcrt.get_osfhandle(pipeout))),
       str(int(msvcrt.get_osfhandle(pipe2in))),
       ], close_fds=True)

# Write to child (could be done with os.write, without os.fdopen)
pipefh = os.fdopen(pipein, 'w')
pipefh.write("Hello from parent.")
pipefh.close()

pipein = os.fdopen(pipe2out, 'r')
print(pipein.read())
pipein.close()

# Wait for the child to finish
subproc.wait()