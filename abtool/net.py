"""Networking helpers: bind addresses, printable URLs, host allowlist, QR code."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from typing import List, Optional, Set


def local_name() -> str:
    """The Mac's Bonjour name (`<name>.local`), which iOS resolves without setup."""
    if sys.platform == "darwin" and shutil.which("scutil"):
        try:
            result = subprocess.run(
                ["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=5
            )
            name = (result.stdout or "").strip()
            if name:
                return name
        except (OSError, subprocess.SubprocessError):
            pass
    return socket.gethostname().split(".")[0]


def lan_ip() -> Optional[str]:
    """Best-effort LAN address: the interface that would carry default traffic."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        address = sock.getsockname()[0]
        return address if not address.startswith("0.") else None
    except OSError:
        return None
    finally:
        sock.close()


def urls(port: int, lan: bool) -> List[str]:
    entries = [f"http://localhost:{port}"]
    if lan:
        name = local_name()
        entries.append(f"http://{name}.local:{port}")
        address = lan_ip()
        if address:
            entries.append(f"http://{address}:{port}")
    return entries


def allowed_hosts(extra: Optional[List[str]] = None) -> Set[str]:
    hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
    name = local_name()
    hosts.add(name.lower())
    hosts.add(f"{name.lower()}.local")
    hosts.add(socket.gethostname().lower())
    address = lan_ip()
    if address:
        hosts.add(address)
    for item in extra or []:
        if item:
            hosts.add(item.strip().lower())
    return hosts


def qr_ascii(text: str) -> Optional[str]:
    try:
        import qrcode
    except Exception:
        return None
    try:
        code = qrcode.QRCode(border=1)
        code.add_data(text)
        code.make(fit=True)
        matrix = code.get_matrix()
    except Exception:
        return None

    lines = []
    for row in range(0, len(matrix), 2):
        top = matrix[row]
        bottom = matrix[row + 1] if row + 1 < len(matrix) else [False] * len(top)
        line = ""
        for index, upper in enumerate(top):
            lower = bottom[index] if index < len(bottom) else False
            if upper and lower:
                line += "\u2588"
            elif upper:
                line += "\u2580"
            elif lower:
                line += "\u2584"
            else:
                line += " "
        lines.append(line)
    return "\n".join(lines)


def print_banner(
    urls_list: List[str],
    token: str,
    lan: bool,
    require_token: bool,
    engine: str,
    data_dir: str,
) -> None:
    primary = urls_list[0] if urls_list else "http://localhost"
    # The QR code is scanned by another device, so it must never say "localhost".
    qr_target = primary
    for url in urls_list:
        if "localhost" not in url and "127.0.0.1" not in url:
            qr_target = url
            break
    link = f"{qr_target}/?k={token}" if require_token else qr_target

    print("")
    print("  Audiobook  -  on-device text to audio")
    print("  " + "-" * 46)
    print(f"  engine   {engine}")
    print(f"  library  {data_dir}")
    if lan:
        print("  mode     LAN ON - other devices on this network can reach these books")
    else:
        print("  mode     this Mac only")
    print("")
    for url in urls_list:
        suffix = f"/?k={token}" if require_token else ""
        print(f"  open     {url}{suffix}")
    # No point scanning a QR code that resolves to localhost on another device.
    qr = qr_ascii(link) if lan else None
    if qr:
        print("")
        print("  Scan on your iPhone:")
        for line in qr.splitlines():
            print("   " + line)
    print("")
    print("  Ctrl-C to stop")
    print("")
    sys.stdout.flush()
