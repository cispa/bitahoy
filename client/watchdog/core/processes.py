import multiprocessing
import os
import sys


def set_proc_name(newname):
    try:
        import setproctitle

        setproctitle.setproctitle("arpjet - " + newname.decode())
    except ImportError:
        from ctypes import byref, cdll, create_string_buffer

        libc = cdll.LoadLibrary("libc.so.6")
        buff = create_string_buffer(len(newname) + 1)
        buff.value = newname
        libc.prctl(15, byref(buff), 0, 0, 0)


def Process(*args, **kwargs):
    if len(args) > 0:
        target = args[0]
    if "target" in kwargs:
        target = kwargs["target"]
        del kwargs["target"]
    if "name" in kwargs:
        name = kwargs["name"]
    else:
        raise Exception("no process name provided")

    def rename_and_run(*args, **kwargs):
        set_proc_name(name.encode())
        with open(os.devnull) as sys.stdin:
            target(*args, **kwargs)

    kwargs["target"] = rename_and_run
    return multiprocessing.Process(*args, **kwargs)
