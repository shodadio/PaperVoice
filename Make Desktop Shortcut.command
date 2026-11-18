#!/bin/bash
# Audiobook Tool - double-click this once to put a shortcut on your Desktop.
#
# It finds the copy of the tool you actually run, drops a shortcut called
# "Audiobook Tool" on your Desktop, and copies today's code into that copy so
# the fixes in this download take effect. Nothing else on your Mac is touched
# and you do not need to type anything.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
SHORTCUT="$HOME/Desktop/Audiobook Tool.command"
MARKER="Created by Audiobook Tool"

bye() {
  printf '\n%s\n\n' "$*"
  printf 'Press Return to close this window. '
  read -r _ || true
  exit 0
}

printf '\n  Audiobook Tool - one-time Desktop shortcut\n'
printf '  ------------------------------------------\n\n'

if [ ! -d "$HOME/Desktop" ]; then
  bye "This Mac has no Desktop folder, so I cannot put a shortcut there."
fi

# Find the copy of the tool that has already been set up (it has a .venv folder).
TOOL=""
FALLBACK=""
while IFS= read -r launcher; do
  [ -n "$launcher" ] || continue
  dir="$(dirname "$launcher")"
  [ "$dir" = "$HERE" ] && continue
  if [ -d "$dir/.venv" ]; then
    TOOL="$dir"
    break
  fi
  [ -z "$FALLBACK" ] && FALLBACK="$dir"
done < <(find "$HOME" -maxdepth 4 -type f -name 'Start Audiobook Tool.command' -not -path '*/Library/*' -print 2>/dev/null)

[ -z "$TOOL" ] && TOOL="$FALLBACK"

if [ -z "$TOOL" ]; then
  bye "I could not find the folder you run the tool from.

  Drag this file into that folder (the one holding \"Install Kokoro Voices.command\"),
  then double-click it there."
fi

printf '  Found the tool in: %s\n' "$TOOL"

# Bring today's code across, so the fixes in this download are in use.
CHANGED=""
if [ -f "$HERE/papervoice/store.py" ] && [ -f "$TOOL/papervoice/store.py" ]; then
  if ! cmp -s "$HERE/papervoice/store.py" "$TOOL/papervoice/store.py"; then
    if cp "$HERE/papervoice/store.py" "$TOOL/papervoice/store.py" 2>/dev/null; then
      CHANGED="yes"
    fi
  fi
fi

# Never overwrite a Desktop item this tool did not create.
if [ -e "$SHORTCUT" ] && ! grep -q "$MARKER" "$SHORTCUT" 2>/dev/null; then
  bye "There is already something called \"Audiobook Tool.command\" on your Desktop
  and this tool did not make it, so I left it alone. Rename or delete that item,
  then double-click this file again."
fi

{
  printf '%s\n' '#!/bin/bash'
  printf '%s\n' "# $MARKER - double-click this to start the tool."
  printf 'cd %s || {\n' "$(printf '%q' "$TOOL")"
  printf '  printf "\\n%%s\\n\\n" "The tool folder has moved or been renamed."\n'
  printf '  printf "\\n%%s\\n\\n" "Open the folder in Finder and double-click Start Audiobook Tool.command instead."\n'
  printf '  printf "Press Return to close this window. "\n'
  printf '  read -r _ || true\n'
  printf '  exit 1\n'
  printf '}\n'
  printf 'exec ./"Start Audiobook Tool.command"\n'
} > "$SHORTCUT" 2>/dev/null

[ -x "$SHORTCUT" ] || chmod +x "$SHORTCUT" 2>/dev/null

if [ ! -x "$SHORTCUT" ]; then
  bye "I could not write the shortcut to your Desktop.

  macOS may be asking whether this window is allowed to use the Desktop folder -
  click Allow, then double-click this file again."
fi

printf '  Shortcut created: %s\n' "$SHORTCUT"
if [ -n "$CHANGED" ]; then
  printf '  Code: updated to this download.\n'
fi

bye "Done. From now on, double-click \"Audiobook Tool\" on your Desktop to start it.
  You can delete this downloaded folder afterwards."
