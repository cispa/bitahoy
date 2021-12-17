import logging
from subprocess import PIPE, Popen  # nosec


def ethtool(interface):
    options = {
        "rx": "on",
        "tx": "on",
        "sg": "on",
        "tso": "on",
        "ufo": "on",
        "gso": "on",
        "lro": "on",
    }
    cmd = ["ethtool", "-K", interface]
    for flag, value in options.items():
        cmd += [flag, value]
    logging.info(str(cmd))
    output = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()  # nosec
    if output[1]:
        logging.info("ethtool: %s", output)


def set_forwarding(enable):
    with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
        f.write("1" if enable else "0")


def setup_interface(interface, forwarding=False):
    ethtool(interface)
    set_forwarding(forwarding)
