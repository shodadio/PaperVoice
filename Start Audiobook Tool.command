#!/bin/bash
# Audiobook Tool - double-click this file in Finder to start it.
# Leave the window open while you use the tool. Close the window (or press Control-C) to stop.

cd "$(dirname "$0")" || exit 1

PORT="${ABTOOL_PORT:-8765}"
DATA="${ABTOOL_DATA:-$HOME/Library/Application Support/Audiobook Tool/library}"
TOKENFILE="$DATA/.access-token"

say_line() { printf '%s\n' "$*"; }

bail() {
  printf '\n%s\n\n' "$*"
  printf 'Press Return to close this window. '
  read -r _ || true
  printf '\n'
  exit 1
}

find_python() {
  for name in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    found="$(command -v "$name" 2>/dev/null)" || continue
    if "$found" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      printf '%s' "$found"
      return 0
    fi
  done
  for found in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -x "$found" ] || continue
    if "$found" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      printf '%s' "$found"
      return 0
    fi
  done
  return 1
}

say_line ""
say_line "  Audiobook Tool"
say_line "  --------------"
say_line ""

if [ "${ABTOOL_LAN:-0}" = "1" ]; then
  MODE="iphone"
else
  MODE="this-mac"
fi

# Something already listening on this port? Just open it.
if /usr/sbin/lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  say_line "  Port $PORT is already in use - opening it in your browser."
  say_line "  (If that page is not the Audiobook Tool, close it and double-click this file again.)"
  open "http://127.0.0.1:$PORT/"
  sleep 3
  exit 0
fi

PY="$(find_python)" || PY=""
if [ -z "$PY" ]; then
  say_line "  This tool needs Python 3.9 or newer, which is free."
  say_line "  Opening the download page in your browser..."
  open "https://www.python.org/downloads/macos/"
  bail "Install Python (the .pkg installer), then double-click this file again."
fi

if [ ! -x .venv/bin/python ]; then
  say_line "  First run: setting up a private Python environment (one time, a few minutes)..."
  say_line ""
  "$PY" -m venv .venv || bail "Could not create the Python environment in this folder."
fi

STAMP=".venv/.papervoice-installed"
WANT="$("$PY" -c 'import hashlib; print(hashlib.sha1(open("pyproject.toml","rb").read()).hexdigest())' 2>/dev/null)" || WANT=""
HAVE="$(cat "$STAMP" 2>/dev/null)" || HAVE=""
if [ -z "$WANT" ] || [ "$HAVE" != "$WANT" ]; then
  say_line "  Installing what the tool needs from the internet (one time, a few minutes)..."
  say_line ""
  .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1
  if ! .venv/bin/python -m pip install -e .; then
    bail "Install failed - see the messages above (usually a network problem)."
  fi
  printf '%s' "$WANT" > "$STAMP"
fi

# Optional neural voices: offer them once, then never ask again.
# Declining changes nothing - the built-in macOS voices stay the fallback.
KOKORO_SKIP=".venv/.kokoro-skipped"
if [ ! -f "$KOKORO_SKIP" ] && command -v osascript >/dev/null 2>&1 \
   && ! .venv/bin/python -c 'import kokoro' >/dev/null 2>&1; then
  PICK="$(osascript -e 'display dialog "Add the Kokoro neural voices? One-time download of about 300 MB, then a 330 MB voice model on first use. Until then the built-in macOS voices are used." buttons {"Use macOS voices", "Install Kokoro"} default button "Install Kokoro" with title "Audiobook Tool" with icon note' 2>/dev/null)" || PICK=""
  case "$PICK" in
    *"Install Kokoro"*)
      printf '\n'
      if ABTOOL_KOKORO_YES=1 "./Install Kokoro Voices.command"; then
        say_line ""
        say_line "  Kokoro is ready - it will be used for narration."
      else
        say_line ""
        say_line "  Kokoro was not installed - the macOS voices will be used."
      fi
      printf '\n'
      ;;
    *"Use macOS voices"*)
      printf 'skipped' > "$KOKORO_SKIP"
      say_line "  Using the built-in macOS voices (install \"Install Kokoro Voices.command\" later for the neural ones)."
      ;;
  esac
fi

mkdir -p "$DATA" || bail "Could not create the library folder: $DATA"

# A fixed access token, so an iPhone home-screen link keeps working between launches.
if [ ! -s "$TOKENFILE" ]; then
  "$PY" -c 'import secrets; print(secrets.token_urlsafe(12))' > "$TOKENFILE" 2>/dev/null
fi
if [ ! -s "$TOKENFILE" ]; then
  bail "Could not write the access token file: $TOKENFILE"
fi
TOKEN="$(cat "$TOKENFILE")"

if [ "$MODE" = "iphone" ]; then
  say_line ""
  say_line "  Mode: this Mac + your iPhone on the same Wi-Fi."
  say_line "  Scan the QR code below with your iPhone camera, then: Share > Add to Home Screen."
  set -- --lan --host 0.0.0.0 --port "$PORT" --token "$TOKEN" --data "$DATA"
else
  say_line "  Mode: this Mac only."
  set -- --port "$PORT" --token "$TOKEN" --data "$DATA"
fi

( sleep 2; open "http://127.0.0.1:$PORT/" ) &

set +e
.venv/bin/python -m papervoice serve "$@"
STATUS=$?
set -e

if [ "$STATUS" -ne 0 ]; then
  bail "The tool stopped unexpectedly (exit $STATUS)."
fi
say_line "  Stopped."
