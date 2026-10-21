"""CodeBlock editor server: confinement, token/origin checks, JSON errors (#24)."""

import http.client
import json
import threading

import pytest

from nos.codeblock.main import (
    MAX_BODY_BYTES,
    PathError,
    confine,
    make_server,
    safe_filename,
)

PROGRAM = 'package demo\nnode Talker { publications { p: std_msgs::String @topic("/p") } }\n'


@pytest.fixture
def server(tmp_path):
    srv = make_server(port=0, workdir=tmp_path)
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def request(server, method, path, body=None, headers=None, raw_body=None):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    hdrs.update(headers or {})
    data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, payload


def post(server, path, body, token=True, headers=None, **kw):
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["X-NOS-Token"] = server.token
    hdrs.update(headers or {})
    status, payload = request(server, "POST", path, body, hdrs, **kw)
    return status, json.loads(payload) if payload else None


class TestBinding:
    def test_binds_loopback_only(self, server):
        assert server.server_address[0] == "127.0.0.1"

    def test_falls_back_when_port_is_taken(self, server):
        taken = server.server_address[1]
        other = make_server(port=taken)
        try:
            assert other.server_address[1] != taken
        finally:
            other.server_close()


class TestGet:
    def test_serves_page_with_token_and_no_external_fonts(self, server):
        status, body = request(server, "GET", "/")
        text = body.decode()
        assert status == 200
        assert server.token in text
        assert "__NOS_TOKEN__" not in text
        assert "googleapis" not in text

    def test_unknown_path(self, server):
        assert request(server, "GET", "/etc/passwd")[0] == 404

    def test_foreign_host_header_rejected(self, server):
        status, _ = request(server, "GET", "/", headers={"Host": "evil.example"})
        assert status == 403


class TestSave:
    def test_saves_inside_workdir(self, server, tmp_path):
        status, data = post(server, "/api/save", {"code": PROGRAM, "filename": "demo.node"})
        assert status == 200 and data["success"]
        assert (tmp_path / "demo.node").read_text() == PROGRAM

    @pytest.mark.parametrize(
        "name",
        [
            "/etc/cron.d/evil.node",
            "../escape.node",
            "sub/../../x.node",
            "a/b.node",
            "..",
            "",
            "plain.txt",
            "~/.bashrc",
            "x\\y.node",
        ],
    )
    def test_rejects_paths_outside_workdir(self, server, tmp_path, name):
        status, data = post(server, "/api/save", {"code": "x", "filename": name})
        assert status == 400 and not data["success"]
        assert not (tmp_path.parent / "escape.node").exists()

    def test_non_string_code(self, server):
        status, data = post(server, "/api/save", {"code": 5, "filename": "a.node"})
        assert status == 400 and not data["success"]


class TestCompile:
    def test_writes_colcon_layout(self, server, tmp_path):
        status, data = post(server, "/api/compile", {"code": PROGRAM, "output_dir": "out"})
        assert status == 200 and data["success"], data
        assert (tmp_path / "out" / "ros2_ws" / "src" / "demo" / "demo" / "talker_node.py").exists()
        assert (tmp_path / "out" / "ros2_ws" / "src" / "demo" / "setup.py").exists()

    def test_compile_errors_are_returned_as_json(self, server):
        status, data = post(server, "/api/compile", {"code": "node {", "output_dir": "out"})
        assert status == 200 and not data["success"]
        assert data["errors"] and "editor.node:" in data["errors"][0]

    @pytest.mark.parametrize("out", ["/tmp/nos-escape", "../nos-escape", "a/../../nos-escape"])
    def test_output_dir_confined(self, server, tmp_path, out):
        status, data = post(server, "/api/compile", {"code": PROGRAM, "output_dir": out})
        assert status == 400 and not data["success"]
        assert not (tmp_path.parent / "nos-escape").exists()


class TestRequestValidation:
    def test_missing_token(self, server, tmp_path):
        status, data = post(server, "/api/save", {"code": "x", "filename": "a.node"}, token=False)
        assert status == 403
        assert not (tmp_path / "a.node").exists()

    def test_wrong_token(self, server):
        status, _ = post(
            server, "/api/save", {"code": "x", "filename": "a.node"}, token=False, headers={"X-NOS-Token": "nope"}
        )
        assert status == 403

    def test_cross_site_origin(self, server, tmp_path):
        status, _ = post(
            server, "/api/save", {"code": "x", "filename": "a.node"}, headers={"Origin": "https://evil.example"}
        )
        assert status == 403
        assert not (tmp_path / "a.node").exists()

    def test_same_origin_allowed(self, server):
        port = server.server_address[1]
        status, _ = post(
            server, "/api/save", {"code": "x", "filename": "a.node"}, headers={"Origin": f"http://127.0.0.1:{port}"}
        )
        assert status == 200

    def test_requires_json_content_type(self, server):
        status, _ = post(
            server, "/api/save", {"code": "x", "filename": "a.node"}, headers={"Content-Type": "text/plain"}
        )
        assert status == 415

    def test_invalid_json(self, server):
        status, data = post(server, "/api/save", None, raw_body=b"{nope")
        assert status == 400 and data["error"] == "Invalid JSON"

    def test_json_must_be_an_object(self, server):
        status, _ = post(server, "/api/save", None, raw_body=b"[1, 2]")
        assert status == 400

    def test_missing_content_length(self, server):
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.putrequest("POST", "/api/save", skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{port}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("X-NOS-Token", server.token)
        conn.endheaders()
        resp = conn.getresponse()
        assert resp.status == 411
        conn.close()

    def test_oversized_body(self, server):
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.putrequest("POST", "/api/save", skip_host=True)
        conn.putheader("Host", f"127.0.0.1:{port}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("X-NOS-Token", server.token)
        conn.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
        conn.endheaders()
        resp = conn.getresponse()
        assert resp.status == 413
        conn.close()

    def test_unknown_post_endpoint(self, server):
        status, _ = post(server, "/api/other", {})
        assert status == 404


class TestHelpers:
    def test_confine_accepts_nested(self, tmp_path):
        assert confine(tmp_path, "a/b").parent == (tmp_path / "a").resolve()

    def test_confine_rejects_symlink_escape(self, tmp_path):
        outside = tmp_path.parent / "outside_dir"
        outside.mkdir(exist_ok=True)
        (tmp_path / "link").symlink_to(outside)
        with pytest.raises(PathError):
            confine(tmp_path, "link/file")

    def test_safe_filename(self):
        assert safe_filename("ok.node") == "ok.node"
        with pytest.raises(PathError):
            safe_filename("../ok.node")
