#!/bin/bash

python3 -m venv env
source env/bin/activate
pip3 install --upgrade bleak Pillow
python3 fortune-gui.py
