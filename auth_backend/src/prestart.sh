#! /usr/bin/env bash

# initialize db
python setup_database.py setup

#Generate keys
python key_op.py generate_if_needed

#Now let the app start
echo "Starting app..."
