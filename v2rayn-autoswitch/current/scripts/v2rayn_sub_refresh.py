#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2rayn 订阅高频刷新: 每 30min (cron) 拉一次订阅, 与库内对比,
- 节点 IP/数量变了 -> 写库 + 飞书通知 (服务商换 IP 时第一时间知道)
- 没变 -> 静默 (不刷用户)
- 拉取失败 -> 保留旧库, 连续失败 >=3 次才告警
只更新订阅, 不动任何节点/端口/代理 (10808 归 c1s2_guard 和看门狗)。
通道: 经库里一个通的 vless 节点 (c1s3/c1s4/c1s5 优先) 做 socks 代理拉订阅。
"""
import importlib.util, json, logging, os, re, sys, time

VDIR = "/home/mac/v2rayN-linux-64"
AS = os.path.join(VDIR, "autoswitch")
STATE = "/home/mac/v2rayN-linux-64/autoswitch/state/sub_refresh.json"
LOGF = os.path.join(VDIR, "autoswitch", "logs", "sub-refresh.log")
FEISHU = "/home/mac/.hermes/scripts/shuimu_daily/deliver_feishu.py"

os.makedirs(os.path.dirname(STATE), exist_ok=True)
os.makedirs(os.path.dirname(LOGF), exist_ok=True)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(LOGF),
                              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("sub-refresh")

spec = importlib.util.spec_from_file_location("autoswitch", os.path.join(AS, "autoswitch.py"))
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)


def notify(msg):
    try:
        import subprocess
        r = subprocess.run([sys.executable, FEISHU, "--text", msg],
                           capture_output=True, text=True, timeout=60)
        ok = "ok" in (r.stdout + r.stderr).lower()
        log.info("飞书通知: %s", "OK" if ok else "FAIL: " + (r.stderr or r.stdout)[:150])
    except Exception as e:
        log.error("飞书通知失败: %s", e)


def probe_ok(server, port_base, xray_bin, timeout, tag):
    ports = au.pick_ports(port_base, 1, log)
    cfg = au.build_probe_config([server], [ports[0]])
    proc = au.start_probe(cfg, xray_bin, [ports[0]], log, tag)
    if proc is None:
        return False
    try:
        import subprocess
        r = subprocess.run(
            ["curl", "-x", "socks5h://127.0.0.1:%d" % ports[0], "-s", "-o", "/dev/null",
             "-w", "%{http_code}", "--max-time", str(timeout),
             "https://www.google.com/generate_204"],
            capture_output=True, text=True, timeout=timeout + 15)
        return r.stdout.strip() == "204"
    except Exception:
        return False
    finally:
        au.stop_probe(proc, log)


def main():
    import sqlite3
    cfg = au.load_config(os.path.join(AS, "config.conf"))
    xray_bin = os.path.join(VDIR, "bin", "xray", "xray")
    db = os.path.join(VDIR, "guiConfigs", "guiNDB.db")

    st = {"fails": 0, "last_ok_ts": 0, "last_sig": ""}
    try:
        st = json.load(open(STATE))
    except Exception:
        pass

    # 通道: 优先 c1s3/c1s4/c1s5, 取第一个通的
    sub_id, sub_url, sub_remark = au.load_sub(db)
    if not sub_id:
        log.error("无启用订阅"); return 4
    servers = au.load_servers(db, sub_id)
    chan = None
    for s in sorted(servers, key=lambda x: au.server_order(au.server_name(x["Remarks"]))):
        name = au.server_name(s["Remarks"])
        if name in ("c1s3", "c1s4", "c1s5"):
            if probe_ok(s, cfg["port_base"], xray_bin, cfg["test_timeout"], "chan"):
                chan = (name, s)
                break
    if chan is None:
        # 兜底: 库里任意节点, 按序试
        for s in sorted(servers, key=lambda x: au.server_order(au.server_name(x["Remarks"]))):
            name = au.server_name(s["Remarks"])
            if probe_ok(s, cfg["port_base"], xray_bin, cfg["test_timeout"], "chan"):
                chan = (name, s)
                break
    if chan is None:
        log.error("没有任何通道节点可用, 本轮跳过")
        st["fails"] = st.get("fails", 0) + 1
        json.dump(st, open(STATE, "w"))
        if st["fails"] == 3:
            notify("[v2rayN] 订阅刷新连续 3 次无通道, 暂时跳过 (代理侧可能全挂)")
        return 1

    chan_name, chan_srv = chan
    log.info("通道: %s", chan_name)

    # 拉订阅 (起一个通道 probe 进程做 socks 代理)
    try:
        ports = au.pick_ports(cfg["port_base"], 1, log)
        proc = au.start_probe(au.build_probe_config([chan_srv], [ports[0]]),
                              xray_bin, [ports[0]], log, "sub")
        if proc is None:
            raise RuntimeError("通道核心启动失败")
        try:
            raw = au.fetch_sub(sub_url, ports[0], cfg["sub_timeout"], log)
        finally:
            au.stop_probe(proc, log)
        content = au.decode_maybe_b64(raw)
        new_servers, skipped = au.parse_links(content)
        if not new_servers:
            raise RuntimeError("解析到 0 节点")
    except Exception as e:
        st["fails"] = st.get("fails", 0) + 1
        log.error("订阅拉取/解析失败: %s", e)
        json.dump(st, open(STATE, "w"))
        if st["fails"] == 3:
            notify("[v2rayN] 订阅刷新连续 3 次失败: %s" % e)
        return 1

    # 新旧对比: 签名 = 节点名 -> (地址, 端口) 排序
    def sig(srvs):
        return json.dumps(
            sorted("%s|%s|%s" % (au.server_name(s["Remarks"]), s["Address"], s["Port"])
                   for s in srvs), ensure_ascii=False)

    new_sig = sig(new_servers)
    old_map = {au.server_name(s["Remarks"]): s for s in servers}
    changed, diffs = new_sig != st.get("last_sig"), []
    if not st.get("last_sig"):
        st["last_sig"] = new_sig  # 首轮只记基线
        log.info("首轮, 记录基线 (%d 节点)", len(new_servers))
        json.dump(st, open(STATE, "w"))
        return 0
    if changed:
        for s in new_servers:
            n = au.server_name(s["Remarks"])
            o = old_map.get(n)
            if o is None:
                diffs.append("+%s(%s:%s)" % (n, s["Address"], s["Port"]))
            elif (o["Address"], o["Port"]) != (s["Address"], s["Port"]):
                diffs.append("~%s: %s:%s -> %s:%s" % (n, o["Address"], o["Port"],
                                                     s["Address"], s["Port"]))
        for n in old_map:
            if n not in {au.server_name(s["Remarks"]) for s in new_servers}:
                diffs.append("-%s" % n)

    if changed:
        # 写库
        try:
            new_servers.sort(key=lambda s: (au.server_order(au.server_name(s["Remarks"])),
                                            au.server_name(s["Remarks"])))
            au.apply_sub_to_db(db, sub_id, new_servers, cfg["backup_keep"], log)
        except Exception as e:
            log.error("写库失败, 保留旧库: %s", e)
            return 3
        st.update(fails=0, last_ok_ts=int(time.time()), last_sig=new_sig)
        json.dump(st, open(STATE, "w"))
        log.info("订阅有变化, 已写库: %s", "; ".join(diffs))
        notify("[v2rayN] 订阅刷新发现变化并已更新库 (%d 节点):\n%s\n通道 %s。"
               "若当前节点 IP 被换了, c1s2 守护/看门狗会自动复检切换。"
               % (len(new_servers), "\n".join(diffs[:12]), chan_name))
    else:
        st.update(fails=0, last_ok_ts=int(time.time()), last_sig=new_sig)
        json.dump(st, open(STATE, "w"))
        log.info("订阅无变化 (%d 节点, %s 等 IP 未变), 静默", len(new_servers), chan_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
