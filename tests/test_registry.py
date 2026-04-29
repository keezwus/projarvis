import pytest
from projarvis.planner.l2.registry import register_constraint, get_plugin, discover_plugins, _registry


class TestRegistry:
    def setup_method(self):
        """Clean registry before each test."""
        _registry.clear()

    def test_register_and_get(self):
        @register_constraint("test_op")
        def dummy(model, variables, args, time_mapper=None):
            pass

        assert get_plugin("test_op") is dummy

    def test_get_unknown(self):
        assert get_plugin("not_registered") is None

    def test_multiple_registrations(self):
        @register_constraint("op_a")
        def op_a(model, variables, args, time_mapper=None):
            pass

        @register_constraint("op_b")
        def op_b(model, variables, args, time_mapper=None):
            pass

        assert get_plugin("op_a") is op_a
        assert get_plugin("op_b") is op_b

    def test_discover_plugins(self):
        discover_plugins()
        # Plugins are deferred; discover should silently succeed
        # even with an empty plugin directory


class TestPluginSignature:
    def setup_method(self):
        _registry.clear()

    def test_plugin_receives_params(self):
        """Verify plugin receives the expected arguments."""
        from unittest.mock import MagicMock
        from ortools.sat.python import cp_model

        plugin_mock = MagicMock()
        register_constraint("mock")(plugin_mock)

        discovered = get_plugin("mock")
        model = cp_model.CpModel()
        variables = {"tasks": {}, "plugins": {}}
        args = {"some_param": 42}
        discovered(model, variables, args, time_mapper=None)

        plugin_mock.assert_called_once_with(model, variables, args, time_mapper=None)
