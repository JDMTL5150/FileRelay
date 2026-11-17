#!/bin/bash

if [[ ! -f "fileshare.py" ]]; then
  echo "[ERROR] fileshare server file missing."
  exit 1
fi

if [[ $# -ne 1 ]]; then
  echo "[ERROR] wrong format. ./start.sh <DEBUG=1:RELEASE=2>"
fi

if [[ "$1" == "1" || "$1" == "dbg" ]]; then
  flask --app fileshare run --debug
elif [[ "$1" == "2" || "$1" == "rel" ]]; then
  flask --app fileshare run --release
else
  echo "[ERROR] option chosen does not exist: $1"
  exit 1
fi
