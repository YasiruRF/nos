"""Import and run generated nodes against a fake rclpy (#12, #29)."""

import importlib.util
import sys
from pathlib import Path

import pytest

from nos.compiler.pipeline import CompilerPipeline
from tests import fake_rclpy

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def load(monkeypatch, tmp_path):
    fake = fake_rclpy.install(monkeypatch)

    def _load(source_or_path: str, file: str):
        text = Path(source_or_path).read_text() if Path(source_or_path).exists() else source_or_path
        result = CompilerPipeline().compile_string(text, "t.node")
        assert result.success, result.errors
        path = tmp_path / file
        path.write_text(result.files[file])
        spec = importlib.util.spec_from_file_location(f"gen_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        return module, fake

    return _load


def test_publisher_node_instantiates(load):
    module, _ = load(str(FIXTURES / "publisher.node"), "talker_node.py")
    node = module.TalkerBase()
    assert node.greeting == "hello"
    assert node.rate == 2.0
    assert node.retries == 3
    assert ("publisher",) == tuple(k for k, _ in node.entities[:1])
    assert any("talker up" in m for _, m in node.get_logger().records)


def test_subscriber_callback_runs(load):
    module, _ = load(str(FIXTURES / "subscriber_service_action.node"), "worker_node.py")
    node = module.WorkerBase()
    kinds = [k for k, _ in node.entities]
    assert kinds.count("subscription") == 1 and kinds.count("publisher") == 1
    node._on_scan_received(object())
    assert any("got scan" in m for _, m in node.get_logger().records)


def test_lifecycle_transitions_run_without_exceptions(load):
    module, fake = load(str(FIXTURES / "lifecycle.node"), "managed_node.py")
    node = module.ManagedBase()
    ok = fake.TransitionCallbackReturn.SUCCESS

    # nothing is created before configure
    assert [k for k, _ in node.entities] == []
    state = object()
    assert node.on_configure(state) is ok
    assert [k for k, _ in node.entities] == ["lifecycle_publisher"]
    assert node.on_activate(state) is ok
    assert node.on_deactivate(state) is ok
    assert node.on_cleanup(state) is ok
    assert [k for k, _ in node.destroyed] == ["publisher"]
    # configure again after cleanup creates a fresh publisher
    assert node.on_configure(state) is ok
    assert [k for k, _ in node.entities].count("lifecycle_publisher") == 2
    assert node.on_shutdown(state) is ok
    assert any("bye" in m for _, m in node.get_logger().records)


def test_plain_node_shutdown_hook_runs_from_main(load):
    src = 'package a\nnode N { on_shutdown -> { self.get_logger().info("bye") } }'
    module, _ = load(src, "n_node.py")
    created = []
    original = module.NBase

    class Spy(original):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            created.append(self)

    module.NBase = Spy
    module.main([])
    assert any("bye" in m for _, m in created[0].get_logger().records)


def test_reentrant_node_uses_multithreaded_executor(load):
    src = 'package a\nnode N { subscriptions { s: std_msgs::String @topic("/s") @reentrant } }'
    module, _ = load(src, "n_node.py")
    node = module.NBase()
    assert node.entities[0][1].kwargs["callback_group"] is node._reentrant_group
