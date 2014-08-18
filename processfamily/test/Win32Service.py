__author__ = 'matth'


import win32service
import win32serviceutil
import win32api
import win32con
import win32event
import win32evtlogutil
import os, sys, string, time
import servicemanager
from processfamily import ProcessFamily
from processfamily.test.FunkyWebServer import FunkyWebServer
from processfamily.test.ParentProcess import ProcessFamilyForTests
import logging
from processfamily.threads import stop_threads


class ProcessFamilyForWin32ServiceTests(ProcessFamilyForTests):

    def get_sys_executable(self):
        return "c:\\Python27\\pythonw.exe"


class ProcessFamilyTestService(win32serviceutil.ServiceFramework):
    _svc_name_ = "ProcessFamilyTest"
    _svc_display_name_ = "Process Family Test Service"
    _svc_description_ = "A testing windows service for processfamily"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg("ProcessFamilyTest stopping ..." )
        self.server.stop()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("ProcessFamilyTest starting up ..." )
        try:
            self.server = FunkyWebServer()
            family = ProcessFamilyForWin32ServiceTests(number_of_child_processes=self.server.num_children)
            family.start()
            servicemanager.LogInfoMsg("ProcessFamilyTest started")
            try:
                try:
                    self.server.run()
                except KeyboardInterrupt:
                    logging.info("Stopping...")
            finally:
                family.stop(timeout=10)
        finally:
            stop_threads()
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