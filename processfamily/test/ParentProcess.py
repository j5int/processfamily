# -*- coding: utf-8 -*-
__author__ = 'matth'

from processfamily import ProcessFamily
from processfamily.test.FunkyWebServer import FunkyWebServer
import time
import logging

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
    server = FunkyWebServer()
    family = ProcessFamilyForTests(number_of_child_processes=server.num_children)
    family.start()
    try:
        try:
            server.run()
        except KeyboardInterrupt:
            pass
    finally:
        family.stop()

    logging.info("Done")