"""Command line interface (#25, #26, part of #28)."""

import subprocess
import sys
from pathlib import Path

import pytest

import nos
import importlib

main = importlib.import_module("nos.compiler.main").main
cli = importlib.import_module("nos.compiler.main")

A = 'package demo\nnode A { publications { p: std_msgs::String @topic("/a") } }\n'
B = 'package demo\nnode B { subscriptions { s: std_msgs::String @topic("/a") } }\n'
LAUNCH = 'package demo\nlaunch L { arguments { x: int = 1 } }\n'
BAD = 'package demo\nnode {'


@pytest.fixture
def src(tmp_path):
    def write(name, text):
        f = tmp_path / name
        f.write_text(text)
        return str(f)
    return write


def pkg_dir(out, name="demo"):
    return Path(out) / "ros2_ws" / "src" / name


class TestBasics:
    def test_version_is_single_sourced(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert nos.__version__ in capsys.readouterr().out

    def test_setup_py_uses_package_version(self):
        text = (Path(__file__).resolve().parents[2] / "setup.py").read_text()
        assert 'version=version' in text

    def test_compile_valid_file(self, src, tmp_path):
        out = tmp_path / "out"
        assert main([src("a.node", A), "-o", str(out), "--no-build"]) == 0
        assert (pkg_dir(out) / "demo" / "a_node.py").exists()
        assert (pkg_dir(out) / "package.xml").exists()

    def test_missing_file(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.node")]) == 1
        assert "File not found" in capsys.readouterr().err

    def test_wrong_extension(self, src, capsys):
        assert main([src("a.txt", A)]) == 1
        assert "Invalid file type" in capsys.readouterr().err

    def test_no_files_is_a_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_cpp_target_is_not_offered(self, src):
        with pytest.raises(SystemExit) as exc:
            main([src("a.node", A), "--target", "cpp"])
        assert exc.value.code == 2

    def test_compile_error_exit_code_and_stderr(self, src, tmp_path, capsys):
        assert main([src("bad.node", BAD), "-o", str(tmp_path / "o")]) == 1
        err = capsys.readouterr().err
        assert "bad.node:2:" in err
        assert not (tmp_path / "o").exists()

    def test_empty_file_fails(self, src, tmp_path, capsys):
        assert main([src("e.node", ""), "-o", str(tmp_path / "o")]) == 1
        assert "nothing to generate" in capsys.readouterr().err

    def test_dry_run_writes_nothing(self, src, tmp_path):
        out = tmp_path / "out"
        assert main([src("a.node", A), "-o", str(out), "--dry-run"]) == 0
        assert not out.exists()

    def test_verbose_prints_summary(self, src, tmp_path, capsys):
        main([src("a.node", A), "-o", str(tmp_path / "o"), "--no-build", "-v"])
        assert "Summary: 1 succeeded, 0 failed" in capsys.readouterr().out

    def test_one_bad_file_does_not_stop_the_others(self, src, tmp_path):
        out = tmp_path / "out"
        code = main([src("bad.node", BAD), src("a.node", A), "-o", str(out), "--no-build"])
        assert code == 1
        assert (pkg_dir(out) / "demo" / "a_node.py").exists()


class TestSharedPackages:
    def test_two_files_one_package_keep_all_entry_points(self, src, tmp_path):
        out = tmp_path / "out"
        assert main([src("a.node", A), src("b.node", B), "-o", str(out), "--no-build"]) == 0
        setup_py = (pkg_dir(out) / "setup.py").read_text()
        assert "'a_node = demo.a_node:main'" in setup_py
        assert "'b_node = demo.b_node:main'" in setup_py

    def test_separate_runs_accumulate(self, src, tmp_path):
        out = tmp_path / "out"
        main([src("a.node", A), "-o", str(out), "--no-build"])
        main([src("b.node", B), "-o", str(out), "--no-build"])
        setup_py = (pkg_dir(out) / "setup.py").read_text()
        assert "a_node = demo.a_node:main" in setup_py
        assert "b_node = demo.b_node:main" in setup_py

    def test_launch_files_are_all_listed(self, src, tmp_path):
        out = tmp_path / "out"
        main([src("a.node", A), src("l.node", LAUNCH), "-o", str(out), "--no-build"])
        assert "'launch/l_launch.py'" in (pkg_dir(out) / "setup.py").read_text()
        assert (pkg_dir(out) / "launch" / "l_launch.py").exists()

    def test_different_packages_get_separate_scaffolds(self, src, tmp_path):
        out = tmp_path / "out"
        main([src("a.node", A), src("c.node", A.replace("demo", "other").replace("node A", "node C")),
              "-o", str(out), "--no-build"])
        assert (pkg_dir(out, "demo") / "package.xml").exists()
        assert (pkg_dir(out, "other") / "package.xml").exists()

    def test_same_output_name_from_two_inputs_is_an_error(self, src, tmp_path, capsys):
        out = tmp_path / "out"
        other = A.replace("/a", "/z")
        code = main([src("a.node", A), src("a2.node", other), "-o", str(out), "--no-build"])
        assert code == 1
        assert "more than one input file" in capsys.readouterr().err


class TestScaffoldContents:
    SRC = ('package demo version "1.2.3" depends: ["geometry_msgs"]\n'
           'node A { publications { p: sensor_msgs::Image @topic("/a") } }\n')

    def build(self, src, tmp_path):
        out = tmp_path / "out"
        assert main([src("a.node", self.SRC), "-o", str(out), "--no-build"]) == 0
        return pkg_dir(out)

    def test_version_from_source(self, src, tmp_path):
        root = self.build(src, tmp_path)
        assert "<version>1.2.3</version>" in (root / "package.xml").read_text()
        assert "version='1.2.3'" in (root / "setup.py").read_text()

    def test_depends_and_interface_packages_become_exec_depends(self, src, tmp_path):
        xml = (self.build(src, tmp_path) / "package.xml").read_text()
        for dep in ("rclpy", "geometry_msgs", "sensor_msgs"):
            assert f"<exec_depend>{dep}</exec_depend>" in xml

    def test_nos_is_not_a_rosdep_key(self, src, tmp_path):
        root = self.build(src, tmp_path)
        assert "<exec_depend>nos</exec_depend>" not in (root / "package.xml").read_text()
        assert "'nos'" in (root / "setup.py").read_text()


class TestBuild:
    def test_colcon_failure_is_reported_once_with_its_reason(self, src, tmp_path, monkeypatch, capsys):
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom: missing dep")
        monkeypatch.setattr(subprocess, "run", fake_run)
        code = main([src("a.node", A), "-o", str(tmp_path / "o")])
        assert code == 1
        err = capsys.readouterr().err
        assert err.count("boom: missing dep") == 1
        assert "Failed to write output" not in err

    def test_build_cache_skips_second_build(self, src, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            (Path(kw["cwd"]) / "install" / "demo").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)
        args = [src("a.node", A), "-o", str(tmp_path / "o")]
        assert main(args) == 0
        assert main(args) == 0
        assert len(calls) == 1
        assert main(args + ["--no-build-cache"]) == 0
        assert len(calls) == 2

    def test_changed_source_rebuilds(self, src, tmp_path, monkeypatch):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            (Path(kw["cwd"]) / "install" / "demo").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)
        main([src("a.node", A), "-o", str(tmp_path / "o")])
        main([src("a.node", A.replace("/a", "/changed")), "-o", str(tmp_path / "o")])
        assert len(calls) == 2

    def test_colcon_missing(self, src, tmp_path, monkeypatch, capsys):
        def fake_run(cmd, **kw):
            raise FileNotFoundError("colcon")
        monkeypatch.setattr(subprocess, "run", fake_run)
        assert main([src("a.node", A), "-o", str(tmp_path / "o")]) == 1
        assert "colcon executable not found" in capsys.readouterr().err


class TestRun:
    def test_run_executes_the_generated_node_path(self, src, tmp_path, monkeypatch):
        seen = []
        monkeypatch.setattr(cli.subprocess, "run",
                            lambda cmd, **kw: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0))
        out = tmp_path / "o"
        assert main([src("a.node", A), "-o", str(out), "--no-build", "--run"]) == 0
        assert seen == [[sys.executable, str(pkg_dir(out) / "demo" / "a_node.py")]]

    def test_run_with_dry_run_is_rejected(self, src, capsys):
        assert main([src("a.node", A), "--dry-run", "--run"]) == 1
        assert "--run cannot be combined with --dry-run" in capsys.readouterr().err

    def test_run_with_several_inputs_is_rejected(self, src, capsys):
        assert main([src("a.node", A), src("b.node", B), "--run"]) == 1
        assert "exactly one input" in capsys.readouterr().err

    def test_run_with_several_nodes_in_one_file_is_rejected(self, src, tmp_path, capsys):
        two = A + "node C { }\n"
        assert main([src("a.node", two), "-o", str(tmp_path / "o"), "--no-build", "--run"]) == 1
        assert "needs a single node" in capsys.readouterr().err

    def test_run_failure_exit_code(self, src, tmp_path, monkeypatch, capsys):
        def boom(cmd, **kw):
            raise subprocess.CalledProcessError(3, cmd)
        monkeypatch.setattr(cli.subprocess, "run", boom)
        assert main([src("a.node", A), "-o", str(tmp_path / "o"), "--no-build", "--run"]) == 1
        assert "Error running node" in capsys.readouterr().err


class TestVscodeInstall:
    def test_does_nothing_unless_asked(self, src, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        main([src("a.node", A), "-o", str(tmp_path / "o"), "--no-build"])
        assert not (tmp_path / "home" / ".vscode").exists()

    def test_install_and_update(self, tmp_path, capsys):
        assert cli.install_vscode_extension(home=tmp_path) is True
        dest = tmp_path / ".vscode" / "extensions" / "vscode-nos"
        assert (dest / "package.json").exists()
        assert "installed" in capsys.readouterr().out

        assert cli.install_vscode_extension(home=tmp_path) is True
        assert "up to date" in capsys.readouterr().out

        (dest / "package.json").write_text('{"version": "0.0.0"}')
        (dest / "stale.txt").write_text("x")
        assert cli.install_vscode_extension(home=tmp_path) is True
        assert "updated" in capsys.readouterr().out
        assert not (dest / "stale.txt").exists()

    def test_failure_is_reported(self, tmp_path, capsys):
        blocker = tmp_path / "blocker"
        blocker.write_text("a file, not a directory")
        assert cli.install_vscode_extension(home=blocker) is False
        assert "could not install" in capsys.readouterr().err

    def test_flag(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cli, "install_vscode_extension", lambda: True)
        assert main(["--install-vscode"]) == 0
