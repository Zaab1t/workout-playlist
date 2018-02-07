"""
    module name
    ~~~~~~~~

    Live reload your beautiful code.

    :author: Carl Bordum Hansen.
    :license: MIT, see LICENSE for details.
"""


__version__ = '0.1.0'
__all__ = ['interact']


import code
import contextlib
import fcntl
import os
import select
import sys
import termios

import pyinotify as inotify


# TODO
#   print exit code after execution
#   support directories
#   cli


class ModuleModifiedError(Exception):
    pass


def runfile(filename):
    """Run *filename* and return context.

    :rtype: dict.
    """
    context = {}
    with open(filename, 'r') as f:
        eval(compile(f.read(), filename, 'exec'), context)
    return context


def clear_events(inotify_fd):
    # only reads, no processing

    can_read_buf = bytearray([0])
    rv = fcntl.ioctl(inotify_fd, termios.FIONREAD, can_read_buf)

    if rv == -1:
        return

    can_read = can_read_buf[0]
    b = os.read(inotify_fd, can_read)
    return b


class LiveReloadInterpreter(code.InteractiveConsole):
    def __init__(self, locals, inotify_fd, filename='<console>', read_fd=None):
        super().__init__(locals=locals, filename=filename)
        self.read_fd = read_fd or sys.stdin.fileno()
        self.inotify_fd = inotify_fd

    def raw_input(self, prompt):
        while True:
            rlist, [], [] = select.select([self.inotify_fd, self.read_fd], [], [])
            print(rlist)

            if self.read_fd in rlist:
                return input(prompt)

            if self.inotify_fd in rlist:
                clear_events(self.inotify_fd)
                raise ModuleModifiedError
    
    # def interact(self):
    #     ...


def get_console(module_name, inotify_fd, stream):
    """Execute module and return `LiveReloadInterpreter` with locals."""
    context = runfile(module_name)
    console = LiveReloadInterpreter(context, inotify_fd, filename=module_name)
    # console.write = stream
    return console


@contextlib.contextmanager
def snakebelt():
    wm = inotify.WatchManager()
    # if we want more inotify events OR (|) them together.
    wm.add_watch(module_name, inotify.IN_MODIFY)
    yield wm.get_fd()
    wm.close()


def interact(module_name, *, stream=None, banner=None, exitmsg=None):
    """Primary function for this module."""
    if stream is None:
        stream = sys.stdout
    if banner is None:
        stream.write('Python %s on %s\n' % (sys.version, sys.platform))

    with snakebelt() as inotify_fd:
        console = get_console(module_name, inotify_fd, stream=stream)
        while "my guitar gently weeps":
            try:
                console.interact()
            except ModuleModifiedError:
                console = get_console(module_name, inotify_fd, stream=stream)

    if exitmsg is None:
        stream.write('\n')
    elif exitmsg != '':
        stream.write('%s\n' % exitmsg)


if __name__ == '__main__':
    interact(sys.argv[1])
