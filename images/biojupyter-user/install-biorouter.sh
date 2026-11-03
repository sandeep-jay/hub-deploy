#!/bin/bash
set -ex
BIOROUTER_VERSION=1.93.2
curl -s -O -L https://github.com/BaranziniLab/biorouter/releases/download/v${BIOROUTER_VERSION}/biorouter-cli_${BIOROUTER_VERSION}_amd64.deb
ls -l
apt-get -y install --no-install-recommends ./biorouter-*.deb
rm -rf /var/lib/apt/lists/*
rm biorouter-*.deb
biorouter --help
