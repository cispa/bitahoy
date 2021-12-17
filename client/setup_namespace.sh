#!/bin/bash
# The idea of this script is to create a new network namespace according to this answer: https://askubuntu.com/a/499850
# This allows us to run tests causing network traffic to run in a separate namespace and hence prevents the network state from changing
# Connection to backend may need additional routing
# Use the created network namespace like "ip netns exec test python3 arpjet.py"

IFACE="wlp2s0"
VIRT1="veth-a" # capture traffic on this one!
VIRT2="veth-b"

# check root
if [ $(id -u) -ne 0 ]
    then echo "Root permissions requires. Please run as root"
    exit
fi

# create network namespace
ip netns add test

# create pair of virtual network interfaces
ip link add $VIRT1 type veth peer name $VIRT2

# change their active ns
ip link set $VIRT1 netns test

# configure IP addresses of virtual interfaces
ip netns exec test ifconfig $VIRT1 up 192.168.69.1 netmask 255.255.255.0
ifconfig $VIRT2 up 192.168.69.254 netmask 255.255.255.0

# configure routing for the ns
ip netns exec test route add default gw 192.168.69.254 dev $VIRT1

# activate ip_forward and establish a NAT rule to forward the traffic coming in from the namespace you created (you have to adjust the network interface and SNAT ip address)
echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -t nat -A POSTROUTING -s 192.168.69.0/24 -o $IFACE -j MASQUERADE

# Allow forwarding between network interface and virtual interface
iptables -A FORWARD -i $IFACE -o $VIRT1 -j ACCEPT
iptables -A FORWARD -o $IFACE -i $VIRT1 -j ACCEPT

