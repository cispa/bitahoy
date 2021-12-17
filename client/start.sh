#!/bin/bash

cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null

which ethtool || (apt-get update && apt-get install ethtool -y)

which cpupower || (apt-get update && apt-get install linux-cpupower -y)

cpupower frequency-set -g conservative

pip3 install -r requirements.txt

./install_libs.sh

python3 arpjet.py
