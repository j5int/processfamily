# -*- coding: utf-8 -*-
__author__ = 'matth'

import os
if __name__ == '__main__':
    pid = os.getpid()
    pid_filename = os.path.join(os.path.dirname(__file__), 'tmp', 'pid', 'p%s.pid' % pid)
    with open(pid_filename, "w") as pid_f:
        pid_f.write("%s\n" % pid)

from processfamily import ProcessFamily, _traceback_str
from processfamily.test.FunkyWebServer import FunkyWebServer
import logging
from processfamily.threads import stop_threads

class ProcessFamilyForTests(ProcessFamily):
    def __init__(self, number_of_child_processes=None, run_as_script=True):
        super(ProcessFamilyForTests, self).__init__(
            child_process_module_name='processfamily.test.ChildProcess',
            number_of_child_processes=number_of_child_processes,
            run_as_script=run_as_script)

    def get_child_process_cmd(self, child_number):
        return super(ProcessFamilyForTests, self).get_child_process_cmd(child_number) + [
            '--process_number', str(child_number+1)]

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting")
    try:
        try:
            server = FunkyWebServer()

            family = ProcessFamilyForTests(number_of_child_processes=server.num_children)
            family.start(timeout=10)
            try:
                try:
                    server.run()
                except KeyboardInterrupt:
                    logging.info("Stopping...")
            finally:
                family.stop(timeout=10)
        finally:
            stop_threads()
    except Exception as e:
        logging.error("Error in process family test parent process: %s\n%s", e, _traceback_str())
    logging.info("Done")