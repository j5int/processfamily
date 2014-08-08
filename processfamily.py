__author__ = 'matth'

class ChildProcess(object):

    def run(self):
        """
        Method representing the thread's activity. You may override this method in a subclass.

        This will be called from the processes main method, after initialising some other stuff.
        """

    def start(self):
        """
        Starts up the the child process.

        You should do this in your child process implementation:

            if __name__ == '__main__':
                MyChildProcess().start()
        """

    def stop_command(self, timeout):
        """
        Will be called from a new thread. The process should do its best to shutdown cleanly if this is called.

        :param timeout The number of milliseconds that the parent process will wait before killing this process.
        """

    def custom_command(self, command, timeout, **kwargs):
        """
        Will be called in a new thread when a custom command is sent from the parent process

        :param command: a string
        :param timeout: The number of milliseconds that the parent process expects the child to take
        :param kwargs: custom keyword arguments (parsed from a json string)
        :return: a json friendly object to return to the parent
        """

    def request_more_time(self, millis):
        """
        During the processing of a command (including the stop command), call this method to request more time.

        :param millis
        """



