#!/usr/bin/env python3
"""v2rayN 时段感知代理守护。

夜间 04:00-08:29：目标是 c1s3，保持 Hermes 的 10808 代理可用。
日间 08:29-次日 04:00：优先 c1s1/c1s2；如果两者都超时，先切到
c1s3 保住代理，立即经 c1s3 更新订阅并复检 c1s1/c1s2，最多连续尝试三轮。
复检到可用节点后切回延迟较小者，三轮都失败才保持 c1s3。

本脚本必须在 v2rayn-switch-runner 内以 root 执行：runner 使用 host PID/network
并直通宿主 /home/mac。所有会操作 10808 的动作都持有 autoswitch.lock，
因此不会与 08:29 的原有 autoswitch 并行。
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

NIGHT_START_MINUTE = 4 * 60
NIGHT_END_MINUTE = 8 * 60 + 29
NIGHT_ORDER = ["c1s3", "c1s4", "c1s1", "c1s2", "c1s5", "c1s801"]
DAY_PREFERRED = ("c1s1", "c1s2")
DAY_ORDER = ["c1s1", "c1s2", "c1s3", "c1s4", "c1s5", "c1s801"]
DAY_C3_RECOVERY_ATTEMPTS = 3

VDIR = Path("/home/mac/v2rayN-linux-64")
AW_DIR = VDIR / "autoswitch"
DB = VDIR / "guiConfigs" / "guiNDB.db"
GUI_CFG = VDIR / "guiConfigs" / "guiNConfig.json"
CFG = VDIR / "guiConfigs" / "config.json"
XRAY = VDIR / "bin" / "xray" / "xray"
LOCK_PATH = AW_DIR / "autoswitch.lock"
LOG_PATH = AW_DIR / "logs" / "mode-guard.log"
STATE_PATH = Path("/home/mac/.hermes/state/v2rayn_mode_guard.json")
FALLBACK_LOG = Path("/home/mac/.hermes/logs/v2rayn_fallback_xray.log")
OWNER_SCRIPT = Path("/home/mac/.hermes/scripts/v2rayn_owner.py")


def operating_mode(now: datetime) -> str:
    """Return the policy mode for Beijing local time."""
    minute = now.hour * 60 + now.minute
    return "night" if NIGHT_START_MINUTE <= minute < NIGHT_END_MINUTE else "day"


def is_autoswitch_quiet_window(now: datetime) -> bool:
    """Reserve 08:28-08:33 Beijing time for the daily autoswitch."""
    minute = now.hour * 60 + now.minute
    return 8 * 60 + 28 <= minute < 8 * 60 + 34


def candidate_order(mode: str) -> list[str]:
    """Return the emergency/recovery order without mutating global policy."""
    if mode == "night":
        return list(NIGHT_ORDER)
    if mode == "day":
        return list(DAY_ORDER)
    raise ValueError("unknown mode: %s" % mode)


def preferred_healthy_order(results: dict | None,
                            names: tuple[str, ...] = DAY_PREFERRED) -> list[str]:
    """Return healthy preferred nodes sorted by measured latency."""
    if not results:
        return []
    good = [name for name in names if results.get(name, {}).get("ok")]
    return sorted(good, key=lambda name: (
        results[name].get("latency_ms") is None,
        results[name].get("latency_ms") if results[name].get("latency_ms") is not None else float("inf"),
    ))


def transition_action(mode: str, current: str | None, *, proxy_ok: bool,
                      target_ok: bool) -> str:
    """Pure policy decision used by tests and the runtime controller."""
    if mode == "night":
        if current == "c1s3" and proxy_ok:
            return "keep_target"
        if target_ok:
            return "switch_target"
        return "keep_current" if proxy_ok else "recover"
    if mode == "day":
        # The 08:29 job owns normal day-node selection.  This guard only
        # recovers a broken proxy and must not churn a healthy node.
        return "keep_current" if proxy_ok else "recover"
    raise ValueError("unknown mode: %s" % mode)


def owner_can_be_replaced(owner: dict) -> bool:
    """Only an empty port or our own fallback may be replaced."""
    return owner.get("owner") in ("none", "fallback")


def gui_blocks_switch(owner: str) -> bool:
    """A GUI process blocks automation only when it owns 10808."""
    return owner == "gui"


def recent_day_target(result: dict, now: datetime, max_age_seconds: int = 90 * 60) -> str | None:
    """Return a recent successful 08:29 formal-node result for one handoff."""
    if not result or result.get("dry_run") or result.get("final_server") not in ("c1s1", "c1s2"):
        return None
    try:
        event = datetime.fromisoformat(str(result["ts"]))
        if event.tzinfo is None:
            event = event.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        age = (now - event).total_seconds()
        if 0 <= age <= max_age_seconds:
            return str(result["final_server"])
    except (KeyError, TypeError, ValueError):
        pass
    return None


def day_handoff_target(result: dict, state: dict, now: datetime) -> str | None:
    """Make the post-08:29 fallback handoff idempotent."""
    if not result or result.get("ts") == state.get("reconciled_result_ts"):
        return None
    return recent_day_target(result, now)


def day_window_key(now: datetime) -> str:
    """Return the date owning the 08:29—next-day 04:00 daytime window."""
    minute = now.hour * 60 + now.minute
    if minute < NIGHT_START_MINUTE:
        return (now.date() - timedelta(days=1)).isoformat()
    return now.date().isoformat()


def day_c3_recovery_terminal(state: dict, now: datetime) -> bool:
    """Avoid refreshing the subscription every two minutes after one incident."""
    return (
        state.get("day_c3_recovery_date") == day_window_key(now)
        and state.get("day_c3_recovery_status") in {
            "recovered", "exhausted", "refresh_failed", "retry_exhausted",
        }
    )


def bj_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def get_logger() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v2rayn-mode-guard")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_last_result() -> dict:
    try:
        return json.loads((AW_DIR / "last_result.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(STATE_PATH) + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def record_state(state: dict, *, mode: str, actual: str | None,
                 owner: str, proxy: bool, error: str | None = None) -> None:
    state.update({
        "mode": mode,
        "desired_node": "c1s3" if mode == "night" else "c1s1_or_c1s2",
        "actual_node": actual,
        "owner": owner,
        "proxy_ok": proxy,
        "checked_at": bj_now().isoformat(timespec="seconds"),
        "last_error": error,
    })
    save_state(state)


def alert_once(state: dict, message: str, logger: logging.Logger, *, cooldown: int = 3600) -> None:
    now = int(time.time())
    last = int(state.get("last_alert_ts", 0) or 0)
    if now - last >= cooldown:
        print("⚠️ v2rayN 时段守护: " + message)
        state["last_alert_ts"] = now
    logger.warning(message)


def load_autoswitch():
    if str(AW_DIR) not in sys.path:
        sys.path.insert(0, str(AW_DIR))
    import autoswitch as aw  # type: ignore
    return aw


def try_autoswitch_lock():
    AW_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK_PATH, "a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


def gui_pids() -> list[int]:
    result = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(path.name)
            raw = (path / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            if not raw:
                continue
            first = raw.split(None, 1)[0]
            if first == "./v2rayN" or first == str(VDIR / "v2rayN") or first.endswith("/v2rayN"):
                result.append(pid)
        except (OSError, ValueError):
            continue
    return sorted(set(result))


def owner_info() -> dict:
    try:
        r = subprocess.run(
            ["python3", str(OWNER_SCRIPT), "10808"],
            capture_output=True, text=True, timeout=10,
        )
        line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "OWNER=other"
    except Exception:
        line = "OWNER=other"
    result = {"owner": "other", "pid": None, "uid": None, "conf": None}
    for key, value in re.findall(r"(OWNER|pid|uid|conf)=([^ ]+)", line):
        if key == "OWNER":
            result["owner"] = value
        elif key == "pid":
            result[key] = int(value) if value.isdigit() else None
        else:
            result[key] = value
    return result


def node_name_from_config(aw) -> str | None:
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        outbounds = cfg.get("outbounds", [])
        candidates = [o for o in outbounds if o.get("tag") == "proxy"] or outbounds
        selected = None
        for outbound in candidates:
            settings = outbound.get("settings", {})
            selected = (settings.get("vnext") or settings.get("servers") or [None])[0]
            if selected:
                break
        if not selected:
            return None
        address, port = selected.get("address"), str(selected.get("port"))
        sub_id, _, _ = aw.load_sub(str(DB))
        if not sub_id:
            return None
        for row in aw.load_servers(str(DB), sub_id):
            if row.get("Address") == address and str(row.get("Port")) == port:
                return aw.server_name(row.get("Remarks", ""))
    except Exception:
        return None
    return None


def find_row(aw, name: str):
    sub_id, _, _ = aw.load_sub(str(DB))
    if not sub_id:
        return None
    for row in aw.load_servers(str(DB), sub_id):
        if aw.server_name(row.get("Remarks", "")) == name:
            return row
    return None


def proxy_ok(aw, cfg: dict) -> bool:
    try:
        ok, _, _ = aw.test_port(
            int(cfg.get("main_port", 10808)),
            cfg.get("test_url", "https://www.google.com/generate_204"),
            int(cfg.get("test_timeout", 8)),
        )
        return bool(ok)
    except Exception:
        return False


def probe_row(aw, row, cfg: dict, logger: logging.Logger, tag: str) -> tuple[bool, float | None]:
    name = aw.server_name(row.get("Remarks", ""))
    try:
        result = aw.probe_servers(
            [row], str(XRAY), int(cfg.get("port_base", 12301)),
            cfg.get("test_url", "https://www.google.com/generate_204"),
            int(cfg.get("test_timeout", 8)), logger, tag,
        )
        item = (result or {}).get(name, {})
        return bool(item.get("ok")), item.get("latency_ms")
    except Exception as exc:
        logger.error("探测 %s 异常: %s", name, exc)
        return False, None


def refresh_subscription_via_current_proxy(aw, cfg: dict, logger: logging.Logger,
                                           attempt: int) -> int:
    """Pull and apply the subscription through the currently working c1s3."""
    sub_id, sub_url, _ = aw.load_sub(str(DB))
    if not sub_id or not sub_url:
        raise RuntimeError("未找到启用的订阅")
    raw = aw.fetch_sub(
        sub_url, int(cfg.get("main_port", 10808)),
        int(cfg.get("sub_timeout", 30)), logger,
    )
    content = aw.decode_maybe_b64(raw)
    servers, skipped = aw.parse_links(content)
    if not servers:
        raise RuntimeError("订阅解析到 0 个节点")
    servers.sort(key=lambda s: (
        aw.server_order(aw.server_name(s.get("Remarks", ""))),
        aw.server_name(s.get("Remarks", "")),
    ))
    aw.apply_sub_to_db(str(DB), sub_id, servers,
                       int(cfg.get("backup_keep", 5)), logger)
    logger.info("c1s3 兜底后的第 %d 次订阅更新完成: %d 个节点, 跳过 %d 行",
                attempt, len(servers), len(skipped))
    for line in skipped[:12]:
        logger.warning("订阅更新跳过行: %s", line)
    return len(servers)


def probe_day_preferred(aw, cfg: dict, logger: logging.Logger, tag: str) -> dict:
    """Probe c1s1/c1s2 from the current subscription and return raw results."""
    rows = []
    for name in DAY_PREFERRED:
        row = find_row(aw, name)
        if row is None:
            logger.warning("日间优先节点 %s 不在当前订阅中", name)
            continue
        rows.append(row)
    if not rows:
        return {}
    results = aw.probe_servers(
        rows, str(XRAY), int(cfg.get("port_base", 12301)),
        cfg.get("test_url", "https://www.google.com/generate_204"),
        int(cfg.get("test_timeout", 8)), logger, tag,
    )
    return results or {}


def ensure_dat_links(logger: logging.Logger) -> None:
    xray_dir = VDIR / "bin" / "xray"
    for name in ("geosite.dat", "geoip.dat"):
        target = xray_dir / name
        if not target.exists():
            target.symlink_to(Path("..") / name)
            logger.info("补齐 xray 数据链接: %s", target)


def fallback_config(aw, row: dict, main_port: int) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "socks", "port": main_port, "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True, "allowTransparent": False},
        }],
        "outbounds": [aw.build_outbound("proxy", row),
                      {"tag": "direct", "protocol": "freedom"}],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                {"type": "field", "domain": ["geosite:cn"], "outboundTag": "direct"},
                {"type": "field", "ip": ["geoip:cn"], "outboundTag": "direct"},
                {"type": "field", "domain": ["geosite:geolocation-!cn"], "outboundTag": "proxy"},
            ],
        },
    }


def write_config(aw, row: dict, cfg: dict, logger: logging.Logger) -> None:
    aw.backup(str(CFG), int(cfg.get("backup_keep", 5)), logger)
    tmp = Path(str(CFG) + ".mode.tmp")
    tmp.write_text(json.dumps(fallback_config(aw, row, int(cfg.get("main_port", 10808))),
                              ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CFG)


def stop_process(pid: int | None, logger: logging.Logger) -> bool:
    if not pid:
        return False
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline:
        if not Path("/proc/%s" % pid).exists():
            return True
        time.sleep(0.5)
    with suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    time.sleep(1)
    gone = not Path("/proc/%s" % pid).exists()
    if not gone:
        logger.error("无法停止旧兜底 xray pid=%s", pid)
    return gone


def start_existing_config(aw, cfg: dict, logger: logging.Logger) -> bool:
    ensure_dat_links(logger)
    FALLBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FALLBACK_LOG.open("ab") as err:
            proc = subprocess.Popen(
                [str(XRAY), "run", "-c", str(CFG)], cwd=str(XRAY.parent),
                stdin=subprocess.DEVNULL, stdout=err, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        up = aw.wait_port(int(cfg.get("main_port", 10808)), 15)
        good = up and proxy_ok(aw, cfg)
        if not good:
            with suppress(ProcessLookupError):
                os.kill(proc.pid, signal.SIGKILL)
            logger.error("兜底 xray 启动后代理校验失败 pid=%s", proc.pid)
        return bool(good)
    except Exception as exc:
        logger.error("启动兜底 xray 异常: %s", exc)
        return False


def switch_fallback(aw, row: dict, cfg: dict, old_owner: dict, *, update_index: bool,
                    logger: logging.Logger) -> tuple[bool, str]:
    """Probe-before-break, switch, verify, and restore the old fallback on failure."""
    old_cfg = CFG.read_bytes() if CFG.exists() else None
    old_gui_cfg = GUI_CFG.read_bytes() if GUI_CFG.exists() else None
    old_name = node_name_from_config(aw)
    old_pid = old_owner.get("pid")

    if old_owner.get("owner") == "gui":
        return False, "GUI 正在持有 10808，按温柔模式不接管"
    if not owner_can_be_replaced(old_owner):
        return False, "10808 持有者无法确认，拒绝替换以避免误杀"

    if old_owner.get("owner") == "fallback" and not stop_process(old_pid, logger):
        return False, "旧兜底 xray 未能退出"

    try:
        write_config(aw, row, cfg, logger)
        if not start_existing_config(aw, cfg, logger):
            raise RuntimeError("新兜底 xray/10808/204 校验失败")
        observed = owner_info()
        if observed.get("owner") != "fallback":
            raise RuntimeError("10808 验证通过但持有者不是预期的 fallback")
        if update_index:
            try:
                aw.set_index_id(str(GUI_CFG), row["IndexId"], int(cfg.get("backup_keep", 5)), logger)
            except Exception as exc:
                logger.error("IndexId 更新失败，但代理已验证可用: %s", exc)
        name = aw.server_name(row.get("Remarks", ""))
        logger.info("已切换兜底节点: %s (原节点=%s)", name, old_name)
        return True, name
    except Exception as exc:
        logger.error("切换到目标节点失败: %s", exc)
        with suppress(Exception):
            if old_cfg is not None:
                CFG.write_bytes(old_cfg)
            if old_gui_cfg is not None:
                GUI_CFG.write_bytes(old_gui_cfg)
        if old_owner.get("owner") == "fallback" and old_cfg is not None:
            if start_existing_config(aw, cfg, logger):
                logger.info("已回滚并恢复旧兜底节点: %s", old_name or "unknown")
            else:
                logger.error("回滚旧兜底节点也失败")
        return False, str(exc)


def recover_day_from_c3(aw, cfg: dict, state: dict, logger: logging.Logger,
                        *, force: bool = False) -> str | None:
    """After a daytime c1s3 fallback, refresh and retry c1s1/c1s2 up to 3 times."""
    now = bj_now()
    today = day_window_key(now)
    if not force and day_c3_recovery_terminal(state, now):
        return None

    state.update({
        "day_c3_recovery_date": today,
        "day_c3_recovery_status": "running",
        "day_c3_recovery_attempts": 0,
        "day_c3_timeout_failures": 0,
        "day_c3_refresh_failures": 0,
        "day_c3_recovery_target": None,
    })
    save_state(state)
    timeout_failures = 0
    refresh_failures = 0

    for attempt in range(1, DAY_C3_RECOVERY_ATTEMPTS + 1):
        state["day_c3_recovery_attempts"] = attempt
        save_state(state)
        try:
            refresh_subscription_via_current_proxy(aw, cfg, logger, attempt)
        except Exception as exc:
            refresh_failures += 1
            state["day_c3_refresh_failures"] = refresh_failures
            logger.error("c1s3 兜底后的第 %d 次订阅更新失败: %s", attempt, exc)
            continue

        after = probe_day_preferred(aw, cfg, logger, "day-c3-after-%d" % attempt)
        good = preferred_healthy_order(after)
        if not good:
            timeout_failures += 1
            state["day_c3_timeout_failures"] = timeout_failures
            logger.warning("第 %d 次订阅更新后 c1s1/c1s2 均超时 (%d/%d)",
                           attempt, timeout_failures, DAY_C3_RECOVERY_ATTEMPTS)
            save_state(state)
            continue

        gui = bool(gui_pids())
        for name in good:
            target = find_row(aw, name)
            if target is None:
                continue
            owner = owner_info()
            switched, detail = switch_fallback(
                aw, target, cfg, owner, update_index=not gui, logger=logger,
            )
            if switched:
                state.update({
                    "day_c3_recovery_status": "recovered",
                    "day_c3_recovery_target": name,
                })
                record_state(state, mode="day", actual=name,
                             owner="fallback", proxy=True)
                logger.info("c1s3 兜底后的订阅复检成功，已切回 %s (第 %d 次)",
                            name, attempt)
                return name
            logger.error("复检到 %s 但切回失败: %s", name, detail)
        logger.warning("第 %d 次复检发现可用日间节点，但切回均失败，继续重试", attempt)

    if timeout_failures >= DAY_C3_RECOVERY_ATTEMPTS:
        status = "exhausted"
        error = "连续 3 次订阅更新后 c1s1/c1s2 均超时，保持 c1s3"
        message = "c1s3 兜底后连续 3 次更新订阅并复检，c1s1/c1s2 仍超时，保持 c1s3。"
    elif refresh_failures == DAY_C3_RECOVERY_ATTEMPTS:
        status = "refresh_failed"
        error = "c1s3 兜底后订阅连续 3 次更新失败，保持 c1s3"
        message = "c1s3 兜底后订阅连续 3 次更新失败，暂保持 c1s3。"
    else:
        status = "retry_exhausted"
        error = "c1s3 兜底后的恢复重试未完成，保持 c1s3"
        message = "c1s3 兜底后的订阅/复检重试未成功，保持 c1s3。"
    state["day_c3_recovery_status"] = status
    current = node_name_from_config(aw) or "c1s3"
    owner = owner_info()
    healthy = proxy_ok(aw, cfg)
    record_state(state, mode="day", actual=current, owner=owner["owner"],
                 proxy=healthy, error=error)
    alert_once(state, message, logger)
    save_state(state)
    return None


def night_tick(aw, cfg: dict, state: dict, logger: logging.Logger) -> int:
    gui = bool(gui_pids())
    owner = owner_info()
    current = node_name_from_config(aw)
    healthy = proxy_ok(aw, cfg)

    if gui and gui_blocks_switch(owner["owner"]):
        # The live GUI owns 10808; never kill or replace it.
        record_state(state, mode="night", actual=current, owner=owner["owner"], proxy=healthy)
        if healthy:
            if current != "c1s3":
                alert_once(state, "GUI 正在持有 10808，未强制切换到 c1s3；当前代理保持可用。", logger)
                save_state(state)
            return 0
        alert_once(state, "GUI 正在运行且 10808 不可用，未杀 GUI；请检查 GUI 核心。", logger)
        save_state(state)
        return 0

    # GUI 进程只是开着但没有持有 10808 时，可以只操作 root fallback。
    # update_index=False 保持用户 GUI 的显示/手动状态不被后台覆盖。
    if current == "c1s3" and healthy:
        record_state(state, mode="night", actual=current, owner=owner["owner"], proxy=True)
        return 0

    target = find_row(aw, "c1s3")
    if target is not None:
        ok, latency = probe_row(aw, target, cfg, logger, "night")
        logger.info("夜间目标 c1s3 探测: %s%s", "OK" if ok else "FAIL",
                    " %.0fms" % latency if latency is not None else "")
        if ok:
            switched, detail = switch_fallback(aw, target, cfg, owner,
                update_index=not gui, logger=logger)
            if switched:
                record_state(state, mode="night", actual="c1s3", owner="fallback", proxy=True)
                return 0
            logger.error("夜间切 c1s3 失败: %s", detail)

    if healthy:
        record_state(state, mode="night", actual=current, owner=owner["owner"], proxy=True,
                     error="c1s3 不可切换，保留当前可用节点")
        alert_once(state, "c1s3 未通过切换校验，已保留当前可用代理。", logger)
        save_state(state)
        return 0

    # Current proxy is down: use the requested c1s3 first, then emergency order.
    for name in candidate_order("night"):
        row = find_row(aw, name)
        if row is None or name == "c1s3":
            continue
        ok, _ = probe_row(aw, row, cfg, logger, "night-recovery")
        if not ok:
            continue
        switched, detail = switch_fallback(aw, row, cfg, owner,
                                            update_index=not gui, logger=logger)
        if switched:
            record_state(state, mode="night", actual=name, owner="fallback", proxy=True,
                         error="c1s3 不可用，使用夜间应急节点")
            alert_once(state, "c1s3 不可用，已切换应急节点 %s。" % name, logger)
            save_state(state)
            return 0
        logger.error("应急切换 %s 失败: %s", name, detail)
    record_state(state, mode="night", actual=current, owner=owner["owner"], proxy=False,
                 error="夜间目标和应急节点均未恢复")
    alert_once(state, "c1s3 及应急节点均未能恢复 10808。", logger)
    save_state(state)
    return 1


def day_tick(aw, cfg: dict, state: dict, logger: logging.Logger) -> int:
    owner = owner_info()
    current = node_name_from_config(aw)
    healthy = proxy_ok(aw, cfg)

    # gentle 模式下主任务只改 DB/IndexId，root fallback 可能仍加载旧节点。
    # 只在同一次成功的 08:29 结果后的短窗口做一次实际兜底交接，
    # 避免持续覆盖用户白天手动使用 c1s3/c1s4。
    result = load_last_result()
    handoff = day_handoff_target(result, state, bj_now())
    if handoff:
        if current == handoff and healthy:
            state["reconciled_result_ts"] = result.get("ts")
        elif owner.get("owner") != "gui":
            target = find_row(aw, handoff)
            if target is not None:
                ok, latency = probe_row(aw, target, cfg, logger, "day-handoff")
                logger.info("08:29 日间交接 %s 探测: %s%s", handoff,
                            "OK" if ok else "FAIL",
                            " %.0fms" % latency if latency is not None else "")
                if ok:
                    switched, detail = switch_fallback(
                        aw, target, cfg, owner, update_index=False, logger=logger
                    )
                    if switched:
                        state["reconciled_result_ts"] = result.get("ts")
                        record_state(state, mode="day", actual=handoff,
                                     owner="fallback", proxy=True)
                        return 0
                    logger.error("08:29 日间交接失败: %s", detail)

    # c1s3 只应是白天的临时兜底。若它仍健康且本日尚未处理过，
    # 立即执行“更新订阅 -> 复检 c1s1/c1s2 -> 切回低延迟节点”；
    # 三轮失败后的状态会落盘，避免每 2 分钟重复刷订阅。
    if current == "c1s3" and healthy and not day_c3_recovery_terminal(state, bj_now()):
        recover_day_from_c3(aw, cfg, state, logger)
        return 0

    if healthy:
        record_state(state, mode="day", actual=current, owner=owner["owner"], proxy=True)
        save_state(state)
        return 0

    if owner.get("owner") == "gui":
        record_state(state, mode="day", actual=current, owner="gui", proxy=False,
                     error="GUI 持有 10808 但代理探测失败")
        alert_once(state, "GUI 正在持有 10808，但代理探测失败；未接管 GUI。", logger)
        save_state(state)
        return 0

    gui = bool(gui_pids())

    # 先同时探测 c1s1/c1s2，不能因为列表顺序而错过延迟更小者。
    preferred_results = probe_day_preferred(aw, cfg, logger, "day-recovery")
    for name in preferred_healthy_order(preferred_results):
        row = find_row(aw, name)
        if row is None:
            continue
        switched, detail = switch_fallback(
            aw, row, cfg, owner, update_index=not gui, logger=logger,
        )
        if switched:
            record_state(state, mode="day", actual=name, owner="fallback", proxy=True,
                         error="代理故障后自动恢复")
            alert_once(state, "代理故障，已恢复到 %s。" % name, logger)
            save_state(state)
            return 0
        logger.error("日间恢复 %s 失败: %s", name, detail)

    # c1s1/c1s2 都超时（或切回失败）时，先切到 c1s3 保住代理；
    # switch 成功后必须在同一 tick 内进入订阅更新/复检流程。
    c3 = find_row(aw, "c1s3")
    if c3 is not None:
        c3_ok, c3_latency = probe_row(aw, c3, cfg, logger, "day-c3-fallback")
        logger.info("日间兜底 c1s3 探测: %s%s", "OK" if c3_ok else "FAIL",
                    " %.0fms" % c3_latency if c3_latency is not None else "")
        if c3_ok:
            switched, detail = switch_fallback(
                aw, c3, cfg, owner, update_index=not gui, logger=logger,
            )
            if switched:
                logger.warning("c1s1/c1s2 日间恢复未成功，已先切到 c1s3，立即开始订阅复检")
                recover_day_from_c3(aw, cfg, state, logger, force=True)
                return 0
            logger.error("日间切 c1s3 失败: %s", detail)

    # c1s3 也不可用时才使用其他应急节点；它们不是白天优选目标。
    emergency = [name for name in candidate_order("day")
                 if name not in DAY_PREFERRED and name != "c1s3"]
    for name in emergency:
        row = find_row(aw, name)
        if row is None:
            continue
        ok, _ = probe_row(aw, row, cfg, logger, "day-emergency")
        if not ok:
            continue
        switched, detail = switch_fallback(aw, row, cfg, owner,
                                            update_index=not gui, logger=logger)
        if switched:
            record_state(state, mode="day", actual=name, owner="fallback", proxy=True,
                         error="优选节点和 c1s3 均不可用，使用日间应急节点")
            alert_once(state, "优选节点和 c1s3 均不可用，已切换应急节点 %s。" % name, logger)
            save_state(state)
            return 0
        logger.error("日间应急切换 %s 失败: %s", name, detail)
    record_state(state, mode="day", actual=current, owner=owner["owner"], proxy=False,
                 error="日间候选节点均未恢复")
    alert_once(state, "日间候选节点均未能恢复 10808。", logger)
    save_state(state)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只输出当前时段，不切换节点")
    args = parser.parse_args(argv)
    now = bj_now()
    mode = operating_mode(now)
    if args.dry_run:
        print("mode=%s bj=%s desired=%s" %
              (mode, now.isoformat(timespec="seconds"),
               "c1s3" if mode == "night" else "c1s1_or_c1s2"))
        return 0

    if is_autoswitch_quiet_window(now):
        get_logger().info("08:29 autoswitch 保护窗口，跳过本 tick")
        return 0

    logger = get_logger()
    lock = try_autoswitch_lock()
    if lock is None:
        logger.info("autoswitch 持锁，跳过本 tick")
        return 0
    try:
        aw = load_autoswitch()
        cfg = aw.load_config(str(AW_DIR / "config.conf"))
        state = load_state()
        return night_tick(aw, cfg, state, logger) if mode == "night" else day_tick(aw, cfg, state, logger)
    except Exception as exc:
        logger.exception("mode guard 未预期异常: %s", exc)
        state = load_state()
        alert_once(state, "守护自身异常: %s" % exc, logger)
        save_state(state)
        return 1
    finally:
        with suppress(Exception):
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
