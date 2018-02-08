"""
    module name
    ~~~~~~~~

    Live reload your beautiful code.

    :author: Carl Bordum Hansen.
    :license: MIT, see LICENSE for details.
"""


__version__ = '0.2.0'
__all__ = ['interact']


import argparse
import code
import contextlib
import fcntl
import os
import runpy
import select
import sys
import termios

import pyinotify as inotify


class ModuleModifiedError(Exception):
    pass


def clear_events(inotify_fd):
    # only reads, no processing

    can_read_buf = bytearray([0])
    rv = fcntl.ioctl(inotify_fd, termios.FIONREAD, can_read_buf)

    if rv == -1:
        return

    can_read = can_read_buf[0]
    b = os.read(inotify_fd, can_read)
    return b


def print_info(stream, msg):
    """Print in green."""
    stream.write('\033[32m[%s]\033[0m\n' % msg)


def print_error(stream, msg):
    """Print in red."""
    stream.write('\033[31m[%s]\033[0m\n' % msg)


class LiveReloadInterpreter(code.InteractiveConsole):
    def __init__(self, locals, inotify_fd, filename='<console>', read_fd=None):
        super().__init__(locals=locals, filename=filename)
        self.read_fd = read_fd or sys.stdin.fileno()
        self.inotify_fd = inotify_fd

    def raw_input(self, prompt):
        while True:
            print(prompt, end='', flush=True)
            rlist, [], [] = \
                select.select([self.inotify_fd, self.read_fd], [], [])

            if self.read_fd in rlist:
                try:
                    return input()
                except EOFError:
                    # XXX: Do we need to clean up here?
                    sys.exit(0)

            if self.inotify_fd in rlist:
                clear_events(self.inotify_fd)
                raise ModuleModifiedError


def get_console(module_name, inotify_fd, stream):
    """Execute module and return `LiveReloadInterpreter` with locals."""
    # TODO: How can we make the script believe it's __main__?
    try:
        context = runpy.run_path(module_name)
    except BaseException as e:
        print_error(stream, '%r failed with %r' % (module_name, e))
        sys.exit(1)

    # print exit code from running context if not 0?
    console = LiveReloadInterpreter(context, inotify_fd, filename=module_name)
    # console.write = stream
    return console


@contextlib.contextmanager
def open_watcher(module_name):
    """Return fd with `inotify.IN_MODIFY` watch on *module_name*."""
    wm = inotify.WatchManager()
    # if we want more inotify events OR (|) them together.
    wm.add_watch(module_name, inotify.IN_MODIFY)
    try:
        yield wm.get_fd()
    finally:
        wm.close()


def interact(module_name, *, stream=None, banner=None, exitmsg=None):
    """Primary function for this module."""
    if stream is None:
        stream = sys.stdout

    if banner is None:
        stream.write('Python %s on %s\n' % (sys.version, sys.platform))

    with open_watcher(module_name) as inotify_fd:
        console = get_console(module_name, inotify_fd, stream=stream)

        while "my guitar gently weeps":
            try:
                console.interact(banner='')
            except ModuleModifiedError:
                stream.write('\n')
                print_info(stream, 'Reloading...')
                # TODO: We need to remove what's being written from stdin as
                # not to confuse our user.
                console = get_console(module_name, inotify_fd, stream=stream)

    if exitmsg is None:
        stream.write('\n')
    elif exitmsg != '':
        stream.write('%s\n' % exitmsg)


def main():
    argp = argparse.ArgumentParser('workout-playlist')
    argp.add_argument('module_path',
                      help='The module to watch.')
    argv = argp.parse_args()
    interact(argv.module_path)


if __name__ == '__main__':
    main()
