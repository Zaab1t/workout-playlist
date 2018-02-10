"""
    module name
    ~~~~~~~~~~~

    Live reload your beautiful code.

    module_name provides the building blocks for integrating live
    reloading into your program, but can also be used as a stand-
    alone executable.

    On its own, it is the equivalent of running
    `python -i [-m] program`, where it automatically reruns when
    you save a file in your program.
"""


__all__ = [
    'ModuleModifiedError',
    'open_watcher',
    'watcher_read',
    'LiveReloadInterpreter',
    'get_console',
    'interact',
]
__version__ = '0.2.0'
__author__ = 'Carl Bordum Hansen'
__license__ = 'MIT'


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


def print_info(stream, msg):
    """Print in green."""
    stream.write('\033[32m[%s]\033[0m\n' % msg)


def print_error(stream, msg):
    """Print in red."""
    stream.write('\033[31m[%s]\033[0m\n' % msg)


class ModuleModifiedError(Exception):
    pass


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


def _clear_events(inotify_fd):
    # only reads, no processing

    can_read_buf = bytearray([0])
    rv = fcntl.ioctl(inotify_fd, termios.FIONREAD, can_read_buf)

    if rv == -1:
        return

    can_read = can_read_buf[0]
    b = os.read(inotify_fd, can_read)
    return b


def watcher_read(prompt, inotify_fd, read_fd):
    """Read a string from *read_fd*, but raise `ModuleModifiedError` if
    *inotify_fd* has been modified.

    :param prompt: is printed to stdout.
    :param inotify_fd: get it from `open_watcher`.
    :param read_fd: the fd to read from.
    :raises EOFError: if the user hits EOF.

    :rtype: string from stdin with trailing newline stripped.
    """
    while True:
        print(prompt, end='', flush=True)
        rlist, [], [] = select.select([inotify_fd, read_fd], [], [])

        if read_fd in rlist:
            return input()

        if inotify_fd in rlist:
            _clear_events(inotify_fd)
            raise ModuleModifiedError


class LiveReloadInterpreter(code.InteractiveConsole):
    def __init__(self, context, filename, inotify_fd, read_fd):
        super().__init__(locals=context, filename=filename)
        self.inotify_fd = inotify_fd
        self.read_fd = read_fd

    def raw_input(self, prompt):
        try:
            return watcher_read(prompt, self.inotify_fd, self.read_fd)
        except EOFError:
            # XXX: Do we need to clean up here?
            sys.exit(0)


def get_console(module_name, inotify_fd, stream):
    """Execute module and return `LiveReloadInterpreter` with locals."""
    # TODO: How can we make the script believe it's __main__?
    context = {}
    try:
        context = runpy.run_path(module_name)
    except SystemExit as e:
        msg = '%r exited with code %s' % (module_name, e.args[0])
        print_error(stream, msg)
    except BaseException as e:
        print_error(stream, '%r failed with %r' % (module_name, e))

    console = LiveReloadInterpreter(
        context, module_name, inotify_fd, sys.stdin.fileno())
    # console.write = stream
    return console


def interact(module_name, *, stream=None, banner=None, exitmsg=None):
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
