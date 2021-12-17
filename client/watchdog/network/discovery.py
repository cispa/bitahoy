from subprocess import PIPE, Popen  # nosec

from watchdog.network.utils import IP, MAC, ArpNode, Interface, NetConfig, Network


def get_own_mac(interface):
    output = Popen(["ip", "link", "show", interface], stdout=PIPE).communicate()[0]  # nosec
    data = output.split()
    return MAC(data[data.index(b"link/ether") + 1].decode())


def mtu(interface):
    output = Popen(["ip", "link", "show", interface], stdout=PIPE).communicate()[0]  # nosec
    data = output.split()
    return int(data[data.index(b"mtu") + 1].decode())


def lookup_macs(ips, filter_device=None):
    result = {}
    for ip in ips:
        result[ip] = None
    with open("/proc/net/arp") as f:
        output = f.readlines()[1:]
        for line in output:
            ipaddr, hwtype, flags, hwaddr, mask, device = line.split()
            if filter_device and device != filter_device:
                continue
            if IP(ipaddr) in ips:
                result[IP(ipaddr)] = MAC(hwaddr)
    return result


def lookup_mac(ip: IP):
    result = lookup_macs([ip])
    if ip in result and result[ip] is not None:
        return result[ip]
    else:
        raise Exception("Failed to lookup ARP for {}".format(ip.debug()))


def get_netconfig() -> NetConfig:
    output = Popen(["ip", "route", "show"], stdout=PIPE).communicate()[0]  # nosec
    gateway = None
    ownip = None
    net = None
    interface = None
    if output.strip() == b"":
        return None
    output_split = output.split(b"\n")
    for line in output_split:
        data = line.split()
        if len(data) > 0 and data[0] == b"default" and b"via" in data:
            gateway = data[data.index(b"via") + 1]
            interface = data[data.index(b"dev") + 1]
        elif interface is not None and len(data) > 0 and data[0] != b"default" and b" " + interface + b" " in line and b"proto" in line:
            ownip = data[data.index(b"src") + 1]
            net = data[0]
            assert interface == data[data.index(b"dev") + 1]
            # copy paste, not necessary
            assert ownip == data[data.index(b"src") + 1]
    ownip = IP(ownip.decode())
    gateway = IP(gateway.decode())
    return NetConfig(
        Interface(interface.decode(), mtu(interface.decode())),
        ArpNode(ownip, get_own_mac(interface.decode())),
        ArpNode(gateway, lookup_mac(gateway)),
        Network(net.decode()),
    )
