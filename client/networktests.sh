#!/bin/bash

bash ./setup_namespace.sh &> /dev/null
ip netns exec test python3.9 -m pytest watchdog -m networktest -vv ${@:1}

