# -*- coding: utf-8 -*-
__author__ = 'matth'

from processfamily.test import ChildProcess
import time
import logging

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting")
    family = ChildProcess.ProcessFamilyForTests(number_of_child_processes=1)
    family.start()
    time.sleep(5)
    family.stop()
    logging.info("Done")