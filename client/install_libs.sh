#!/bin/bash

git submodule update --init

cd addon-sdk-python
sudo python3 ./setup.py install


cd ../DeviceIdentifier
sudo python3 ./setup.py install