from projarvis.planner.l1.registry import (
    register_distributor,
    get_distributor,
    discover_distributors,
)


class TestRegisterDistributor:
    def test_register_and_lookup(self):
        @register_distributor("test_strategy")
        def my_fn(model, variables, params, windows, time_mappers, epoch):
            pass

        fn = get_distributor("test_strategy")
        assert fn is my_fn

    def test_unknown_returns_none(self):
        assert get_distributor("nonexistent") is None


class TestDiscoverDistributors:
    def test_discovers_plugins_package(self):
        # Should not raise — l1.plugins package exists (even if empty)
        discover_distributors()
