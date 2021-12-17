#!/bin/sh

set -e

adduser --gecos pi --disabled-password pi
adduser pi sudo
echo "pi:pi" | chpasswd
passwd -l root
