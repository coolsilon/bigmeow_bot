#!/bin/sh

set -e

. /venv/bin/activate

# TODO not sure why poetry bundle would fail to populate path correctly
export PYTHONPATH=/venv/lib/python3.11/site-packages/

exec python -m bigmeow.index
