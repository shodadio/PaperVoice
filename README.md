# PaperVoice

Turn EPUB, PDF, DOCX and Markdown files into chaptered audiobooks on your own machine.

Free, on-device, no accounts, no API keys, no uploads. You add a document, pick the
chapters and the narrator, and get back a chaptered **M4B** or a single **MP3** you can
play in Books, VLC, or anywhere else.

## What it does

- **Reads what you already have.** EPUB, PDF, DOCX, TXT, Markdown and HTML. MOBI, AZW3,
  RTF, ODT, FB2 and LIT also work when [Calibre](https://calibre-ebook.com) is installed,
  since it converts them to EPUB first.
- **Splits books into chapters** in reading order, so you can narrate only what you want
  and the finished M4B keeps real chapter marks.
- **Narrates locally.** The neural Kokoro voices run on this Mac's GPU where the GPU can
  do the work, and on the CPU for the few steps Apple's Metal cannot run; the built-in macOS
  voices are always there as an instant fallback.
- **Serves a phone-first web app** on your own Wi-Fi, so the iPhone can add books and
  download finished audio without a cable.
- **Cancels and resumes.** Stop a render halfway and the chapters already finished are kept;
  pressing Process again picks up from there.
- **Stays on your computer.** Nothing is uploaded, no text or audio leaves the machine, and
  the library is a folder you can back up or delete.

## Requirements

- macOS with **Python 3.9 or newer** — install it free from
  [python.org/downloads/macos](https://www.python.org/downloads/macos/) if `python3` is missing.
  The optional Kokoro voices are only published for Python 3.10–3.12, so the Kokoro
  installer switches the tool to 3.12 when that Python is on the Mac, and otherwise
  says plainly which Python to install.
- An internet connection for the first run only: it downloads the Python packages it needs
  (a few minutes).
- Optional: an iPhone or iPad on the same Wi-Fi, for the phone launcher.

## Quick start, no terminal

1. Download `AudiobookTool-mac.zip` from the [latest release](../../releases/latest) and
   unzip it somewhere permanent.
2. Double-click **Start Audiobook Tool.command**. The first time, macOS may refuse because
   the file came from the internet: right-click it → **Open** → **Open**.
3. A Terminal window sets things up and your browser opens the tool by itself. Leave that
   window open while you use it; closing it (or Control-C) stops the tool.
4. Add a document, tick the chapters you want, choose a voice, press **Process into audio**,
   then name the file and download it.

On the iPhone: double-click **Start Audiobook Tool (iPhone).command** instead. The Terminal
shows a QR code — scan it with the camera, open the link in Safari, then **Share → Add to
Home Screen**. The phone only works while the Mac is awake and the tool is running.

Finished files land in **Files → Downloads** on iOS. Long-press one, **Share**, then
**Books** to get it into your library with its chapters.

## Voices

| Engine | What it is | Setup |
| --- | --- | --- |
| **Kokoro** | Neural voices, 12 narrators (US and UK, female and male), 24 kHz, uses the Apple GPU | One double-click, see below |
| **macOS voices** | Apple's built-in `say` voices — robotic but perfectly usable, and instant | None, always available |
| **Silent** | A placeholder that writes silent audio; only used when neither of the above can load | — |

The tool picks Kokoro automatically once it is installed, and falls back to the macOS
voices whenever it is not. Nothing breaks if you never install Kokoro.

### Installing Kokoro (optional, one time)

Double-click **Install Kokoro Voices.command** in the tool folder and click **Install
Kokoro**. It downloads about 300 MB of Python packages, then a further ~330 MB voice model
the first time it actually narrates. Everything is free and on-device.

The start-up launcher also offers this on its first run — choosing "Use macOS voices" there
only silences that prompt; the installer file still works whenever you want the better
voices.

### Is it using the GPU?

Under the voice picker the page says which chip is doing the work — "Narrating on the
Apple GPU" or "Narrating on the CPU". The launcher sets the one PyTorch setting Kokoro
needs for Metal on a Mac, so on an Apple Silicon Mac it should say the GPU.

If it says the CPU on an Apple Silicon Mac, the installed Kokoro is too old to choose a
device: double-click **Install Kokoro Voices.command** again to update it. On an Intel Mac
there is no GPU option and the CPU is the fastest available path.

## Where your books live

```
~/Library/Application Support/Audiobook Tool/library
```

Each document gets its own folder there with its chapter audio and an `export/` folder
holding `book.m4b` and `book.mp3`. The access token that protects the web app is kept in the
same folder (`.access-token`), so an iPhone home-screen link keeps working between launches.
Delete a book from the app to remove it, or delete the whole folder to start fresh.

## Running from source

```bash
git clone https://github.com/shodadio/PaperVoice.git
cd PaperVoice
python3 -m venv .venv
.venv/bin/pip install -e .            # add ".[kokoro]" for the neural voices
.venv/bin/papervoice serve            # then open http://localhost:8765
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--port 8765` | Port to listen on |
| `--lan` | Bind to your network and print a QR code so a phone can connect |
| `--token TOKEN` | Use a fixed access token instead of a random one |
| `--data DIR` | Library folder (default `./library`) |
| `--max-upload-mb 200` | Largest accepted document |
| `--no-auth` | Disable the token — only on a network you trust |
| `--allow-host HOST` | Accept an extra `Host` header, e.g. when behind a proxy |

Environment overrides: `ABTOOL_PORT`, `ABTOOL_DATA`, `ABTOOL_LAN` (used by the iPhone
launcher), `ABTOOL_KOKORO_DEVICE` (`mps` or `cpu` — the launchers already set the
`PYTORCH_ENABLE_MPS_FALLBACK=1` that Metal needs, so `cpu` is the one worth trying if the
GPU path misbehaves or you want to compare speeds).

## How it stays private

The server binds to `127.0.0.1` unless you ask for `--lan`. In LAN mode every request needs
the access token, and a `Host` allowlist rejects requests addressed to unknown hostnames, so
a random site you visit cannot reach your library. There is no telemetry and no network
call except the package and model downloads you explicitly start.

## Limitations

- DRM-free documents only. Scanned PDFs need OCR first — you will see "No readable text found".
- The macOS `say` engine is macOS-only; on other systems the tool runs, but narration needs
  Kokoro installed.
- Long books take a while. The progress bar shows a per-chapter estimate; cancelling keeps
  whatever has finished.

## License

[MIT](LICENSE) © 2026 shodadio
