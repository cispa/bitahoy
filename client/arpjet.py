#!/usr/bin/env python3

import os
import sys


def escalate_privileges():

    if os.getuid() != 0:
        print("restarting as root!")  # noqa: T001
        os.execv("/usr/bin/sudo", [sys.executable] + ["./" + sys.argv[0]] + sys.argv[1:])  # nosec


escalate_privileges()


def main():
    if sys.version_info <= (3, 9):
        print("WARNING: running old python version. Please use >= 3.9")  # noqa: T001
    if len(sys.argv) == 1:
        import watchdog.modules.master

        watchdog.modules.master.Master().run()
        return
    else:
        if sys.argv[1] == "script":
            if len(sys.argv) < 3:
                print("no script provided")  # noqa: T001
            else:
                import importlib

                importlib.import_module(sys.argv[2]).script_main()
        else:
            print("Command not found:", sys.argv[1])  # noqa: T001
        exit(1)


main()
