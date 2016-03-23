__author__ = 'matth'

import os
#I do this for Win32Service when name != '__main__', because when running as a service the main method isn't actually called
if __name__ != '__main__':
    pid = os.getpid()
    pid_filename = os.path.join(os.path.dirname(__file__), 'tmp', 'pid', 's%s.pid' % pid)
    if not os.path.exists(os.path.dirname(pid_filename)):
        os.makedirs(os.path.dirname(pid_filename))
    with open(pid_filename, "w") as pid_f:
        pid_f.write("%s\n" % pid)

import win32service
import win32serviceutil
import win32api
import win32con
import win32event
import win32evtlogutil
import sys, string, time
import servicemanager
from processfamily import _traceback_str
from processfamily.test import Config
from processfamily.test.FunkyWebServer import FunkyWebServer
from processfamily.test.ParentProcess import ProcessFamilyForTests
import logging
from processfamily.threads import stop_threads


class ProcessFamilyForWin32ServiceTests(ProcessFamilyForTests):

    def get_sys_executable(self):
        return Config.pythonw_exe


class ProcessFamilyTestService(win32serviceutil.ServiceFramework):
    _svc_name_ = Config.svc_name
    _svc_display_name_ = "Process Family Test Service"
    _svc_description_ = "A testing windows service for processfamily"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)

    def SvcStop(self):
        #We need 12 seconds = cos we might have to wait 10 for a frozen child
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=12000)
        servicemanager.LogInfoMsg("ProcessFamilyTest stopping ..." )
        logging.info("Stop request received")
        self.server.stop()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("ProcessFamilyTest starting up ..." )
        try:
            logging.getLogger().setLevel(logging.INFO)
            self.server = FunkyWebServer()
            logging.info("Starting process family")
            family = ProcessFamilyForWin32ServiceTests(number_of_child_processes=self.server.num_children)
            self.server.family = family
            family.start(timeout=10)
            servicemanager.LogInfoMsg("ProcessFamilyTest started")
            try:
                logging.info("Starting HTTP server")
                self.server.run()
            except KeyboardInterrupt:
                logging.info("Stopping...")
        except Exception as e:
            logging.error("Error in windows service: %s\n%s", e, _traceback_str())
        finally:
            logging.info("Stopping")
            stop_threads(exclude_thread_fn=lambda t: t.getName() != 'MainThread')
        servicemanager.LogInfoMsg("ProcessFamilyTest stopped" )

def usage():
    try:
        fname = os.path.split(sys.argv[0])[1]
    except:
        fname = sys.argv[0]
    print "Usage: '%s [options] install|update|remove|start [...]|stop|restart [...]|debug [...]'" % fname
    print "Options for 'install' and 'update' commands only:"
    print " --username domain\\username : The Username the service is to run under"
    print " --password password : The password for the username"
    print " --startup [manual|auto|disabled|delayed] : How the service starts, default = manual"
    print " --interactive : Allow the service to interact with the desktop."
    print " --perfmonini file: .ini file to use for registering performance monitor data"
    print " --perfmondll file: .dll file to use when querying the service for"
    print "   performance data, default = perfmondata.dll"
    print "Options for 'start' and 'stop' commands only:"
    print " --wait seconds: Wait for the service to actually start or stop."
    print "                 If you specify --wait with the 'stop' option, the service"
    print "                 and all dependent services will be stopped, each waiting"
    print "                 the specified period."
    sys.exit(1)

def HandleCommandLine():
    win32serviceutil.HandleCommandLine(ProcessFamilyTestService, serviceClassString='processfamily.test.Win32Service.ProcessFamilyTestService')

if __name__ == '__main__':
    HandleCommandLine()