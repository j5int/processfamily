
__author__ = 'matth'

from processfamily import ProcessFamily
import time

if __name__ == '__main__':
    print "Starting"
    family = ProcessFamily(
        child_process_module_name='processfamily.test.ChildProcess',
        number_of_child_processes=1,
        run_as_script=True)
    family.start()
    time.sleep(5)
    family.stop()
    print "Done"