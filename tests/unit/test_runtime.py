"""nos.runtime against a fake rclpy (#27)."""

import importlib

import pytest

from tests import fake_rclpy


@pytest.fixture
def rt(monkeypatch):
    fake = fake_rclpy.install(monkeypatch)
    runtime = importlib.import_module("nos.runtime")
    qos = importlib.import_module("nos.runtime.qos")
    return types_ns(runtime=runtime, qos=qos, fake=fake)


def types_ns(**kw):
    import types
    return types.SimpleNamespace(**kw)


class TestPublicApi:
    def test_exports(self, rt):
        assert set(rt.runtime.__all__) == {"NOSNode", "NOSLifecycleNode", "create_qos_profile"}

    def test_dead_decorators_module_is_gone(self, rt):
        with pytest.raises(ImportError):
            importlib.import_module("nos.runtime.decorators")


class TestCreateQosProfile:
    def test_defaults(self, rt):
        q = rt.qos.create_qos_profile()
        assert q.reliability is fake_rclpy.ReliabilityPolicy.RELIABLE
        assert q.durability is fake_rclpy.DurabilityPolicy.VOLATILE
        assert q.history is fake_rclpy.HistoryPolicy.KEEP_LAST
        assert q.depth == 10

    def test_all_values(self, rt):
        q = rt.qos.create_qos_profile(
            reliability="best_effort", durability="transient_local", history="keep_all",
            depth=3, lifespan=1.5, deadline=2.0, liveliness="manual_by_topic",
            liveliness_lease_duration=4.0)
        assert q.reliability is fake_rclpy.ReliabilityPolicy.BEST_EFFORT
        assert q.durability is fake_rclpy.DurabilityPolicy.TRANSIENT_LOCAL
        assert q.history is fake_rclpy.HistoryPolicy.KEEP_ALL
        assert q.depth == 3
        assert q.lifespan.seconds == 1.5 and q.deadline.seconds == 2.0
        assert q.liveliness is fake_rclpy.LivelinessPolicy.MANUAL_BY_TOPIC
        assert q.liveliness_lease_duration.seconds == 4.0

    @pytest.mark.parametrize("kwargs", [
        {"reliability": "relieable"}, {"reliability": None}, {"durability": "forever"},
        {"history": "keep_some"}, {"liveliness": "sometimes"},
        {"depth": 0}, {"depth": -1}, {"depth": "5"}, {"depth": True}, {"depth": 2.5},
    ])
    def test_invalid_values_raise(self, rt, kwargs):
        with pytest.raises(ValueError):
            rt.qos.create_qos_profile(**kwargs)

    def test_error_message_lists_the_choices(self, rt):
        with pytest.raises(ValueError, match="best_effort, reliable"):
            rt.qos.create_qos_profile(reliability="relieable")

    @pytest.mark.parametrize("factory,reliability,durability,depth", [
        ("reliable_qos", "RELIABLE", "VOLATILE", 10),
        ("best_effort_qos", "BEST_EFFORT", "VOLATILE", 10),
        ("sensor_qos", "BEST_EFFORT", "VOLATILE", 10),
        ("parameter_qos", "RELIABLE", "VOLATILE", 1),
        ("latching_qos", "RELIABLE", "TRANSIENT_LOCAL", 1),
    ])
    def test_presets(self, rt, factory, reliability, durability, depth):
        q = getattr(rt.qos, factory)()
        assert q.reliability.name == reliability
        assert q.durability.name == durability
        assert q.depth == depth


class TestNOSNode:
    def test_hooks_are_noops(self, rt):
        node = rt.runtime.NOSNode("n")
        assert node.on_init() is None
        assert node.on_shutdown() is None

    def test_logging_helpers(self, rt):
        node = rt.runtime.NOSNode("n")
        node.log_info("hello", points=3)
        node.log_warn("careful")
        node.log_error("bad", code=7)
        node.log_debug("dbg")
        assert node.get_logger().records == [
            ("info", "hello | points=3"),
            ("warn", "careful"),
            ("error", "bad | code=7"),
            ("debug", "dbg"),
        ]


class TestNOSLifecycleNode:
    def test_transitions_succeed(self, rt):
        node = rt.runtime.NOSLifecycleNode("n")
        ok = rt.fake.TransitionCallbackReturn.SUCCESS
        state = object()
        for transition in ("on_configure", "on_activate", "on_deactivate", "on_cleanup", "on_shutdown"):
            assert getattr(node, transition)(state) is ok

    def test_shutdown_transition_runs_the_user_hook(self, rt):
        calls = []

        class Sub(rt.runtime.NOSLifecycleNode):
            def on_nos_shutdown(self):
                calls.append("hook")

        Sub("n").on_shutdown(object())
        assert calls == ["hook"]

    def test_cleanup_does_not_run_the_shutdown_hook(self, rt):
        calls = []

        class Sub(rt.runtime.NOSLifecycleNode):
            def on_nos_shutdown(self):
                calls.append("hook")

        Sub("n").on_cleanup(object())
        assert calls == []

    def test_no_unused_state_attributes(self, rt):
        node = rt.runtime.NOSLifecycleNode("n")
        assert not hasattr(node, "_nos_configured")
        assert not hasattr(rt.runtime.NOSNode("n"), "_nos_initialized")
