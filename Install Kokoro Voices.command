#!/bin/bash
# Audiobook Tool - install the Kokoro neural voices (one time).
# Double-click this file in Finder; nothing needs typing. The tool keeps
# working with the built-in macOS voices whether or not you install these.

cd "$(dirname "$0")" || exit 1

PY=".venv/bin/python"

esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

command -v osascript >/dev/null 2>&1 && GUI=1 || GUI=""

alert() {  # short messages only: dialogs do not wrap multi-line text well here
  if [ -n "$GUI" ]; then
    osascript -e "display dialog \"$(esc "$1")\" buttons {\"OK\"} default button \"OK\" with title \"Audiobook Tool\" with icon note" >/dev/null 2>&1 || true
  fi
  printf '%s\n' "$1"
}

confirm() {  # $1 = question, $2 = accept button. 0 means yes.
  [ "${ABTOOL_KOKORO_YES:-0}" = "1" ] && return 0
  [ -n "$GUI" ] || return 1   # never start a big download without a click
  answer="$(osascript -e "display dialog \"$(esc "$1")\" buttons {\"Use macOS voices\", \"$2\"} default button \"$2\" with title \"Audiobook Tool\" with icon caution" 2>/dev/null)" || return 1
  case "$answer" in
    *"$2"*) return 0 ;;
    *) return 1 ;;
  esac
}

printf '\n  Audiobook Tool - Kokoro voices\n'
printf '  -----------------------------\n\n'

if [ ! -x "$PY" ]; then
  alert "Start the tool once first (double-click \"Start Audiobook Tool.command\"), then run this installer."
  exit 1
fi

if "$PY" -c 'import kokoro' >/dev/null 2>&1; then
  alert "The Kokoro voices are already installed. Start the tool and it will use them automatically."
  exit 0
fi

if ! confirm "Install the Kokoro neural voices now? About 300 MB of packages, then a 330 MB voice model on first use. Free and on-device, nothing is uploaded." "Install Kokoro"; then
  alert "Using the built-in macOS voices. Run \"Install Kokoro Voices.command\" any time to add Kokoro."
  exit 1
fi

printf '  Downloading and installing. This takes a few minutes on a normal connection.\n\n'
if ! "$PY" -m pip install -e ".[kokoro]"; then
  alert "The download did not finish (usually a network problem). The macOS voices still work; run this file again to retry."
  exit 1
fi

if "$PY" -c 'import kokoro' >/dev/null 2>&1; then
  printf '\n'
  alert "Kokoro voices installed. Start the tool and it will narrate with them automatically."
  exit 0
fi

alert "Kokoro downloaded but would not load. The tool will keep using the macOS voices; run this file again to retry."
exit 1
