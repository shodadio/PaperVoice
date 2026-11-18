#!/bin/bash
# Audiobook Tool for your iPhone - double-click this file in Finder.
# Same tool as "Start Audiobook Tool.command", but it also lets your iPhone
# reach it over Wi-Fi and shows a QR code to scan.

cd "$(dirname "$0")" || exit 1
ABTOOL_LAN=1 exec ./"Start Audiobook Tool.command"
