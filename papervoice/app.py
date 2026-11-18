"""HTTP layer: upload a document, choose chapters, process, download."""

from __future__ import annotations

import secrets
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional,Tuple
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)

from . import ingest, proc, store, tts

COOKIE = "papervoice"
STATIC = Path(__file__).parent / "static"

_MEDIA = {
    "app.js": "text/javascript; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "text/javascript; charset=utf-8",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
}


def create_app(
    data_dir: Path,
    token: str,
    allow_hosts: set,
    require_token: bool = False,
    max_upload_mb: int = 200,
) -> FastAPI:
    store.init(data_dir)
    app = FastAPI(title="Audiobook", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def host_guard(request: Request, call_next):
        host = _host_only(request.headers.get("host", ""))
        if host and host not in allow_hosts and not host.endswith(".local"):
            return JSONResponse(
                {"detail": f"Host '{host}' is not allowed. Start the server with --allow-host {host}."},
                status_code=403,
            )
        return await call_next(request)

    def require_auth(request: Request) -> None:
        if not require_token:
            return
        supplied = request.cookies.get(COOKIE) or request.headers.get("x-papervoice-token") or ""
        if not secrets.compare_digest(supplied, token):
            raise HTTPException(
                status_code=401,
                detail="Open the link printed in the Mac's terminal - it carries the access token.",
            )

    # ---------- app shell -------------------------------------------------

    @app.get("/")
    def index(request: Request, k: Optional[str] = None):
        if k and secrets.compare_digest(k, token):
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(
                COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365, path="/"
            )
            return response
        if require_token:
            supplied = request.cookies.get(COOKIE) or ""
            if not secrets.compare_digest(supplied, token):
                return HTMLResponse(_locked_page(), status_code=401)
        return FileResponse(STATIC / "index.html", media_type="text/html", headers=_no_store())

    @app.get("/{name}")
    def static_file(name: str):
        if name not in _MEDIA:
            raise HTTPException(status_code=404)
        path = STATIC / name
        if not path.exists():
            raise HTTPException(status_code=404)
        cache = "no-store" if name in ("sw.js", "app.js", "styles.css") else "public, max-age=3600"
        return FileResponse(path, media_type=_MEDIA[name], headers={"Cache-Control": cache})

    # ---------- api -------------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/engines")
    def engines(_: None = Depends(require_auth)):
        return {"engines": tts.describe(), "default": tts.default_engine_name()}

    @app.get("/api/books")
    def list_books(_: None = Depends(require_auth)):
        return {"books": [store.summary(book) for book in store.all_books()]}

    @app.post("/api/books")
    async def upload(file: UploadFile = File(...), _: None = Depends(require_auth)):
        limit = max(1, max_upload_mb) * 1024 * 1024
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "doc").suffix)
        size = 0
        try:
            with handle as sink:
                while True:
                    piece = await file.read(1 << 20)
                    if not piece:
                        break
                    size += len(piece)
                    if size > limit:
                        raise HTTPException(status_code=413, detail=f"File is larger than {max_upload_mb} MB.")
                    sink.write(piece)
            if size == 0:
                raise HTTPException(status_code=400, detail="That file is empty.")
            try:
                book = store.new_book(Path(handle.name), file.filename or "document")
            except ingest.IngestError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"Could not read that file: {exc}") from exc
            return store.summary(book)
        finally:
            Path(handle.name).unlink(missing_ok=True)

    @app.get("/api/books/{book_id}")
    def get_book(book_id: str, _: None = Depends(require_auth)):
        return store.summary(_load(book_id))

    @app.patch("/api/books/{book_id}")
    def patch_book(book_id: str, payload: dict, _: None = Depends(require_auth)):
        book = _load(book_id)
        if proc.is_running(book_id):
            raise HTTPException(status_code=409, detail="Wait for the current render to finish.")
        if "include" in payload and isinstance(payload["include"], list):
            wanted = {int(value) for value in payload["include"] if str(value).isdigit()}
            for chapter in book["chapters"]:
                chapter["include"] = chapter["idx"] in wanted
        for field in ("engine", "voice", "format"):
            value = payload.get(field)
            if isinstance(value, str) and value:
                book[field] = value[:80]
        if payload.get("speed") is not None:
            try:
                book["speed"] = min(2.5, max(0.5, float(payload["speed"])))
            except (TypeError, ValueError):
                pass
        if isinstance(payload.get("title"), str) and payload["title"].strip():
            book["title"] = payload["title"].strip()[:160]
        if book.get("status") in ("done", "error"):
            book["status"] = "ready"
            book["error"] = ""
        store.save(book)
        return store.summary(book)

    @app.post("/api/books/{book_id}/process")
    def process(book_id: str, _: None = Depends(require_auth)):
        book = _load(book_id)
        if proc.is_running(book_id):
            raise HTTPException(status_code=409, detail="Already processing.")
        if not any(chapter.get("include") for chapter in book["chapters"]):
            raise HTTPException(status_code=400, detail="Select at least one chapter.")
        try:
            proc.start(book_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        book["status"] = "processing"
        book["error"] = ""
        store.save(book)
        return store.summary(book)

    @app.post("/api/books/{book_id}/cancel")
    def cancel(book_id: str, _: None = Depends(require_auth)):
        _load(book_id)
        if not proc.cancel(book_id):
            raise HTTPException(status_code=409, detail="Nothing is being processed.")
        return {"ok": True}

    @app.get("/api/books/{book_id}/download")
    def download(
        book_id: str,
        request: Request,
        format: str = "m4b",
        name: Optional[str] = None,
        _: None = Depends(require_auth),
    ):
        book = _load(book_id)
        fmt = "mp3" if format.lower().startswith("mp3") else "m4b"
        path = store.book_dir(book_id) / "export" / f"book.{fmt}"
        if not path.exists():
            raise HTTPException(status_code=409, detail="Not processed yet.")
        label = name or book.get("title") or "audiobook"
        media = "audio/mpeg" if fmt == "mp3" else "audio/mp4"
        return _range_response(path, _download_name(label, fmt), media, request)

    @app.delete("/api/books/{book_id}")
    def delete_book(book_id: str, _: None = Depends(require_auth)):
        _load(book_id)
        if proc.is_running(book_id):
            raise HTTPException(status_code=409, detail="Wait for the render to finish.")
        store.remove(book_id)
        return {"ok": True}

    return app


def _load(book_id: str) -> dict:
    try:
        return store.load(book_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="That document is no longer in the library.") from exc


def _host_only(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        return value[1:end].lower() if end > 0 else value.lower()
    return value.rsplit(":", 1)[0].lower()


def _no_store() -> dict:
    return {"Cache-Control": "no-store"}


def _download_name(label: str, fmt: str) -> str:
    cleaned = unicodedata.normalize("NFKC", label)
    cleaned = "".join(ch for ch in cleaned if ch not in '\\/:*?"<>|' and ord(ch) >= 32)
    cleaned = " ".join(cleaned.split()).strip(". ")[:120] or "audiobook"
    return f"{cleaned}.{fmt}"


def _ascii_fallback(filename: str) -> str:
    ascii_only = filename.encode("ascii", "ignore").decode("ascii").strip()
    return ascii_only or "audiobook"


def _range_response(path: Path, filename: str, media: str, request: Request):
    size = path.stat().st_size
    disposition = (
        f'attachment; filename="{_ascii_fallback(filename)}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": disposition,
        "Content-Type": media,
        "Cache-Control": "no-store",
    }
    wanted = _parse_range(request.headers.get("range"), size)
    status = 200
    start, length = 0, size
    if wanted is not None:
        start, end = wanted
        length = end - start + 1
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(length)
    return StreamingResponse(_stream(path, start, length), status_code=status, headers=headers)


def _parse_range(header: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    if not header or not header.lower().startswith("bytes=") or size <= 0:
        return None
    spec = header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    raw_start, raw_end = spec.split("-", 1)
    try:
        if raw_start == "":
            length = int(raw_end)
            if length <= 0:
                return None
            start = max(0, size - length)
            end = size - 1
        else:
            start = int(raw_start)
            end = int(raw_end) if raw_end else size - 1
    except ValueError:
        return None
    if start >= size:
        return None
    return start, min(end, size - 1)


def _stream(path: Path, start: int, length: int, chunk: int = 256 * 1024):
    with open(str(path), "rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            block = handle.read(min(chunk, remaining))
            if not block:
                break
            remaining -= len(block)
            yield block


def _locked_page() -> str:
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audiobook - locked</title>
<style>
 body{margin:0;min-height:100vh;display:grid;place-items:center;background:#161311;color:#f4ece0;
      font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px}
 div{max-width:32rem}h1{font:600 1.4rem/1.3 Georgia,serif;margin:0 0 .75rem}
 p{margin:.5rem 0;color:#c9bfae}code{background:#241f1a;padding:.15em .4em;border-radius:4px}
</style></head><body><div>
<h1>This library needs its access link</h1>
<p>Open the URL printed in the Mac's terminal exactly as shown &mdash; it ends in
<code>?k=&hellip;</code> and sets a cookie on this device.</p>
<p>That token is what keeps the rest of the network out.</p>
</div></body></html>"""
