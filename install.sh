#!/bin/bash -e

sudo pip3 install pynvim
sudo pip3 install libtmux
sudo apt install python3.7
ls /usr/bin/ | grep python
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.6 1
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 2
sudo update-alternatives --config python3
echo "OK"
