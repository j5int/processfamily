__author__ = 'matth'

class ChildProcess(object):

    def main(self, args):
        pass

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


