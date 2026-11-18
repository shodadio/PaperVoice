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

# Kokoro is only published for Python 3.10, 3.11 and 3.12. The tool's own
# environment may have been made by the 3.9 that ships with macOS or by a
# 3.13+, and pip then reports "No matching distribution found for kokoro".
# So check the version first and, when this Mac has a usable one, switch the
# environment over to it.
py_ok() {
  "$1" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1
}

py_label() {
  "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || printf 'an unknown version'
}

find_kokoro_python() {
  for name in python3.12 python3.11 python3.10; do
    found="$(command -v "$name" 2>/dev/null)" || continue
    py_ok "$found" && { printf '%s' "$found"; return 0; }
  done
  for found in \
    /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
    /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 \
    /opt/homebrew/bin/python3.10 /usr/local/bin/python3.10 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.10/bin/python3; do
    [ -x "$found" ] || continue
    py_ok "$found" && { printf '%s' "$found"; return 0; }
  done
  return 1
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

GOOD=""
if ! py_ok "$PY"; then
  GOOD="$(find_kokoro_python)" || GOOD=""
  if [ -z "$GOOD" ]; then
    open "https://www.python.org/downloads/macos/" >/dev/null 2>&1 || true
    alert "The Kokoro voices need Python 3.10, 3.11 or 3.12. This Mac has $(py_label "$PY") and no 3.10-3.12 was found, so they cannot be installed yet. I opened the free Python page - install Python 3.12, then run this file again. Nothing is broken in the meantime: the macOS voices keep working."
    exit 1
  fi
fi

if ! confirm "Install the Kokoro neural voices now? About 300 MB of packages, then a 330 MB voice model on first use. Free and on-device, nothing is uploaded." "Install Kokoro"; then
  alert "Using the built-in macOS voices. Run \"Install Kokoro Voices.command\" any time to add Kokoro."
  exit 1
fi

if [ -n "$GOOD" ]; then
  # Rebuilding the environment stops any copy of the tool that is using it.
  if /usr/sbin/lsof -nP -iTCP:"${ABTOOL_PORT:-8765}" -sTCP:LISTEN >/dev/null 2>&1; then
    alert "The Audiobook Tool is still open. Close its Terminal window, then run this file again - the one-time Python switch needs it stopped first."
    exit 1
  fi
  printf '  This Mac runs the tool on Python %s, which cannot install Kokoro.\n' "$(py_label "$PY")"
  printf '  Setting the tool up on Python %s first (one time, a few minutes).\n\n' "$(py_label "$GOOD")"
  rm -rf .venv
  if ! "$GOOD" -m venv .venv; then
    alert "Could not set up the Python environment in this folder. Your books are safe and the macOS voices still work; double-click \"Start Audiobook Tool.command\" to try again."
    exit 1
  fi
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
  if ! "$PY" -m pip install -e .; then
    alert "The tool's own parts did not reinstall (usually a network problem). Double-click \"Start Audiobook Tool.command\" to finish that, then run this file again."
    exit 1
  fi
fi

printf '  Downloading and installing. This takes a few minutes on a normal connection.\n\n'
if ! "$PY" -m pip install -e ".[kokoro]"; then
  alert "The download did not finish. Check the connection and run this file again; the macOS voices keep working until then."
  exit 1
fi

if "$PY" -c 'import kokoro' >/dev/null 2>&1; then
  printf '\n'
  alert "Kokoro voices installed. Start the tool and it will narrate with them automatically."
  exit 0
fi

alert "Kokoro downloaded but would not load. The tool will keep using the macOS voices; run this file again to retry."
exit 1
