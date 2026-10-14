#!/usr/bin/env python3
"""v2rayN 时段守护策略测试。"""
from __future__ import annotations

import importlib.util
import logging
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

MODULE_PATH = str(__file__.replace("v2rayn_mode_guard_test.py", "v2rayn_mode_guard.py"))
spec = importlib.util.spec_from_file_location("v2rayn_mode_guard_under_test", MODULE_PATH)
assert spec and spec.loader
mg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mg)

BJ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 9, 16, 13, 0, tzinfo=BJ)


class ModeGuardPolicyTest(unittest.TestCase):
    def test_day_and_night_boundaries(self):
        self.assertEqual(mg.operating_mode(datetime(2026, 9, 16, 3, 59, tzinfo=BJ)), "day")
        self.assertEqual(mg.operating_mode(datetime(2026, 9, 16, 4, 0, tzinfo=BJ)), "night")
        self.assertEqual(mg.operating_mode(datetime(2026, 9, 16, 8, 28, tzinfo=BJ)), "night")
        self.assertEqual(mg.operating_mode(datetime(2026, 9, 16, 8, 29, tzinfo=BJ)), "day")

    def test_preferred_order_uses_latency_not_config_order(self):
        results = {
            "c1s1": {"ok": True, "latency_ms": 800.0},
            "c1s2": {"ok": True, "latency_ms": 650.0},
        }
        self.assertEqual(mg.preferred_healthy_order(results), ["c1s2", "c1s1"])

    def test_terminal_state_is_scoped_to_daytime_window(self):
        state = {"day_c3_recovery_date": "2026-09-16", "day_c3_recovery_status": "exhausted"}
        self.assertEqual(mg.day_window_key(NOW), "2026-09-16")
        self.assertTrue(mg.day_c3_recovery_terminal(state, NOW))
        self.assertFalse(mg.day_c3_recovery_terminal(state, NOW.replace(day=17)))

        early = NOW.replace(day=17, hour=2)
        prior_window = {"day_c3_recovery_date": "2026-09-16", "day_c3_recovery_status": "exhausted"}
        self.assertEqual(mg.day_window_key(early), "2026-09-16")
        self.assertTrue(mg.day_c3_recovery_terminal(prior_window, early))
        next_window = {"day_c3_recovery_date": "2026-09-17", "day_c3_recovery_status": "exhausted"}
        self.assertFalse(mg.day_c3_recovery_terminal(next_window, early))


class C3RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.logger = logging.getLogger("mode-guard-test")
        self.saved = []

    def common_patches(self, refresh, probe, switches):
        rows = {name: {"Remarks": name} for name in ("c1s1", "c1s2")}
        return [
            patch.object(mg, "bj_now", return_value=NOW),
            patch.object(mg, "save_state", side_effect=lambda state: self.saved.append(dict(state))),
            patch.object(mg, "refresh_subscription_via_current_proxy", side_effect=refresh),
            patch.object(mg, "probe_day_preferred", side_effect=probe),
            patch.object(mg, "find_row", side_effect=lambda _aw, name: rows.get(name)),
            patch.object(mg, "gui_pids", return_value=[]),
            patch.object(mg, "owner_info", return_value={"owner": "fallback", "pid": 1}),
            patch.object(mg, "switch_fallback", side_effect=switches),
            patch.object(mg, "record_state"),
            patch.object(mg, "alert_once"),
        ]

    def test_refresh_then_switches_to_lower_latency_preferred_node(self):
        refresh = lambda *args: 6
        probes = iter([
            {"c1s1": {"ok": False, "latency_ms": 8000}, "c1s2": {"ok": False, "latency_ms": 8000}},
            {"c1s1": {"ok": True, "latency_ms": 700}, "c1s2": {"ok": True, "latency_ms": 500}},
        ])
        probe = lambda *args: next(probes)
        switches = lambda _aw, row, _cfg, _owner, **_kwargs: (True, row["Remarks"])
        with self.enter_contexts(self.common_patches(refresh, probe, switches)):
            result = mg.recover_day_from_c3(object(), {}, self.state, self.logger, force=True)
        self.assertEqual(result, "c1s2")
        self.assertEqual(self.state["day_c3_recovery_status"], "recovered")
        self.assertEqual(self.state["day_c3_recovery_target"], "c1s2")
        self.assertEqual(self.state["day_c3_recovery_attempts"], 2)

    def test_three_post_update_timeouts_keep_c1s3(self):
        refresh = lambda *args: 6
        probe = lambda *args: {
            "c1s1": {"ok": False, "latency_ms": 8000},
            "c1s2": {"ok": False, "latency_ms": 8000},
        }
        switches = lambda *args, **kwargs: self.fail("不应在三轮超时后切换到日间节点")
        with self.enter_contexts(self.common_patches(refresh, probe, switches)):
            with patch.object(mg, "node_name_from_config", return_value="c1s3"), \
                 patch.object(mg, "proxy_ok", return_value=True):
                result = mg.recover_day_from_c3(object(), {}, self.state, self.logger, force=True)
        self.assertIsNone(result)
        self.assertEqual(self.state["day_c3_recovery_status"], "exhausted")
        self.assertEqual(self.state["day_c3_timeout_failures"], 3)
        self.assertEqual(self.state["day_c3_recovery_attempts"], 3)

    def enter_contexts(self, contexts):
        class Contexts:
            def __enter__(inner_self):
                for context in contexts:
                    context.__enter__()
                return inner_self

            def __exit__(inner_self, exc_type, exc, tb):
                for context in reversed(contexts):
                    context.__exit__(exc_type, exc, tb)
                return False

        return Contexts()


if __name__ == "__main__":
    unittest.main(verbosity=2)
