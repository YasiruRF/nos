"""NOS Visual CodeBlock Editor Server.

A small local web app for building NOS programs from blocks.  It can write
files, so it is locked down:

- it binds to the loopback interface only;
- every request must carry the ``Host`` of the server (DNS-rebinding guard);
- POST requests must be ``application/json``, carry the per-session token that
  is embedded in the served page, and (if the browser sends one) come from the
  server's own origin, so other web pages cannot drive it;
- file names and output directories are confined to the directory the server
  was started in;
- request bodies are size-limited.
"""

import http.server
import json
import logging
import secrets
import sys
import webbrowser
from importlib import resources
from pathlib import Path
from typing import Optional

from nos.compiler.pipeline import CompilerPipeline

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8080
MAX_BODY_BYTES = 1024 * 1024
TOKEN_HEADER = "X-NOS-Token"
TOKEN_PLACEHOLDER = "__NOS_TOKEN__"
SOURCE_SUFFIX = ".node"


def load_index_html() -> str:
    """The editor page, packaged as ``static/index.html``."""
    return resources.files(__package__).joinpath("static", "index.html").read_text(encoding="utf-8")


class PathError(ValueError):
    """A client-supplied path points outside the allowed directory."""


def confine(base: Path, candidate: str) -> Path:
    """Resolve ``candidate`` relative to ``base`` and require it to stay inside ``base``."""
    if not candidate or "\x00" in candidate:
        raise PathError("empty or invalid path")
    base = base.resolve()
    target = (base / candidate).resolve()  # an absolute candidate replaces base, caught below
    try:
        target.relative_to(base)
    except ValueError:
        raise PathError(f"path escapes the working directory: {candidate!r}") from None
    return target


def safe_filename(name: str) -> str:
    """A bare ``*.node`` file name: no directories, no absolute paths, no traversal."""
    if (not name or name != Path(name).name or name in (".", "..")
            or "\\" in name or "\x00" in name):
        raise PathError(f"invalid file name: {name!r}")
    if not name.endswith(SOURCE_SUFFIX):
        raise PathError(f"file name must end with {SOURCE_SUFFIX}")
    return name


class CodeBlockHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the code block visual editor."""

    # set on the handler class by make_server()
    token: str = ""
    workdir: Path = Path.cwd()
    allowed_hosts: frozenset = frozenset()

    def log_message(self, format, *args):
        logger.debug("%s - %s", self.address_string(), format % args)

    # -- helpers -------------------------------------------------------------

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in self.allowed_hosts

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # not a cross-site browser request (e.g. curl, tests)
        return origin in {f"http://{host}" for host in self.allowed_hosts}

    def _read_json(self) -> Optional[dict]:
        """Validate the POST request and return its JSON object (or send an error)."""
        if not self._origin_ok():
            self._send_json(403, {"success": False, "error": "Forbidden origin"})
            return None

        supplied = self.headers.get(TOKEN_HEADER, "")
        if not secrets.compare_digest(supplied.encode(), self.token.encode()):
            self._send_json(403, {"success": False, "error": "Missing or invalid token"})
            return None

        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._send_json(415, {"success": False, "error": "Content-Type must be application/json"})
            return None

        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_json(411, {"success": False, "error": "Valid Content-Length required"})
            return None
        if length < 0:
            self._send_json(400, {"success": False, "error": "Invalid Content-Length"})
            return None
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"success": False, "error": "Request body too large"})
            return None

        try:
            params = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"success": False, "error": "Invalid JSON"})
            return None
        if not isinstance(params, dict):
            self._send_json(400, {"success": False, "error": "JSON object expected"})
            return None
        return params

    # -- routes --------------------------------------------------------------

    def do_GET(self):
        if not self._host_ok():
            self.send_error(403, "Forbidden host")
            return
        if self.path in ("/", "/index.html"):
            body = load_index_html().replace(TOKEN_PLACEHOLDER, self.token).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        if not self._host_ok():
            self._send_json(403, {"success": False, "error": "Forbidden host"})
            return
        if self.path not in ("/api/save", "/api/compile"):
            self._send_json(404, {"success": False, "error": "Unknown endpoint"})
            return

        params = self._read_json()
        if params is None:
            return

        try:
            if self.path == "/api/save":
                self._save(params)
            else:
                self._compile(params)
        except PathError as e:
            status = 400
            key = "error" if self.path == "/api/save" else "errors"
            self._send_json(status, {"success": False, key: str(e) if key == "error" else [str(e)]})
        except Exception as e:  # keep the connection answerable whatever goes wrong
            logger.exception("request failed")
            key = "error" if self.path == "/api/save" else "errors"
            self._send_json(500, {"success": False, key: str(e) if key == "error" else [str(e)]})

    def _save(self, params: dict) -> None:
        code = params.get("code", "")
        if not isinstance(code, str):
            raise PathError("'code' must be a string")
        filename = safe_filename(str(params.get("filename", "program" + SOURCE_SUFFIX)))
        filepath = confine(self.workdir, filename)
        filepath.write_text(code, encoding="utf-8")
        self._send_json(200, {"success": True, "path": str(filepath)})

    def _compile(self, params: dict) -> None:
        code = params.get("code", "")
        if not isinstance(code, str):
            raise PathError("'code' must be a string")
        out_dir = confine(self.workdir, str(params.get("output_dir", "./src")))

        pipeline = CompilerPipeline({"auto_build": False})
        result = pipeline.compile_string(code, "editor" + SOURCE_SUFFIX)
        if not result.success:
            self._send_json(200, {"success": False, "errors": result.errors})
            return

        # Same colcon-style package layout the command line writes.
        if not pipeline.write_outputs(result, str(out_dir)):
            self._send_json(200, {"success": False, "errors": result.errors or ["could not write output"]})
            return
        self._send_json(200, {"success": True, "path": str(out_dir)})


def make_server(port: int = DEFAULT_PORT, workdir: Optional[Path] = None,
                host: str = "127.0.0.1") -> http.server.HTTPServer:
    """Create (but do not start) the editor server.

    Binds to ``host`` only; if ``port`` is taken, an ephemeral port is used.
    ``port=0`` always picks a free port.  The chosen port is
    ``server.server_address[1]`` and the session token is ``server.token``.
    """
    handler = type("BoundCodeBlockHandler", (CodeBlockHandler,), {})
    try:
        server = http.server.HTTPServer((host, port), handler)
    except OSError:
        if port == 0:
            raise
        server = http.server.HTTPServer((host, 0), handler)

    bound_port = server.server_address[1]
    handler.token = secrets.token_urlsafe(32)
    handler.workdir = (workdir or Path.cwd()).resolve()
    handler.allowed_hosts = frozenset({f"127.0.0.1:{bound_port}", f"localhost:{bound_port}"})
    server.token = handler.token
    return server


def main(argv: Optional[list] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    server = make_server()
    port = server.server_address[1]
    url = f"http://localhost:{port}/"
    print(f"Starting NOS Visual CodeBlock editor on {url}")
    print(f"Files are saved under {server.RequestHandlerClass.workdir}")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down CodeBlock editor server.")
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
