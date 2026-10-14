#!/usr/bin/env python3
"""v2rayn_c1s2_guard.py — c1s2 专用守护 (每5min, 跑在 runner 容器, -u 0)

状态机:
  代理 OK 且当前=c1s2          -> 静默
  代理 OK 且当前!=c1s2         -> 探 c1s2, 通则切回 c1s2 + 飞书通知; 不通静默
  代理 FAIL                    -> 探 c1s2: 通则重启 xray 恢复;
                                  不通探 c1s3, 通则切 c1s3 兜底 + 飞书通知;
                                  全不通 + 飞书告警(10min 冷却)
切换 = 精确杀旧 xray(按 10808 监听 inode 持有者) -> 写 config.json -> 起新 xray -> 验证
通知走 deliver_feishu.py 直发; 常态零输出(配合 no_agent cron: stdout 非空才投递).
"""
import os, sys, json, time, glob, subprocess, sqlite3

VDIR = '/home/mac/v2rayN-linux-64'
DB = VDIR + '/guiConfigs/guiNDB.db'
XRAY = VDIR + '/bin/xray/xray'
CFG = VDIR + '/guiConfigs/config.json'
STATE = '/home/mac/.hermes/state/v2rayn_c1s2_guard.json'
sys.path.insert(0, VDIR + '/autoswitch')
import autoswitch as aw
sys.path.insert(0, '/home/mac/.hermes/scripts/shuimu_daily')
import deliver_feishu as df

log = aw.Log(VDIR + '/autoswitch/logs/c1s2-guard.log')
COOLDOWN = 600  # 通知冷却 10min


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'node': 'unknown', 'last_notify_ts': 0}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + '.tmp'
    json.dump(st, open(tmp, 'w'))
    os.replace(tmp, STATE)


def notify(title, body):
    st = load_state()
    now = time.time()
    if now - st.get('last_notify_ts', 0) < COOLDOWN:
        log.info('通知冷却中, 跳过: %s' % title)
        return
    try:
        ok, detail = df.send_markdown('### %s\n%s' % (title, body))
        log.info('飞书通知 %s: %s' % (title, detail))
        if ok:
            st['last_notify_ts'] = now
            save_state(st)
    except Exception as e:
        log.info('飞书通知异常: %s' % e)


def proxy_ok():
    for _ in range(2):
        r = subprocess.run(
            ['curl', '-x', 'socks5h://127.0.0.1:10808', '-o', '/dev/null', '-s',
             '-w', '%{http_code}', '--max-time', '10',
             'https://www.google.com/generate_204'],
            capture_output=True, text=True, timeout=20)
        if r.stdout.strip() == '204':
            return True
    return False


def current_node():
    """config.json 当前 outbound -> 节点名 (按 address:port 反查库)"""
    try:
        o = json.load(open(CFG))['outbounds'][0]
        st = o.get('settings', {})
        s = (st.get('vnext') or [{}])[0] or (st.get('servers') or [{}])[0]
        addr, port = s.get('address'), s.get('port')
        con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
        sub_id, _, _ = aw.load_sub(DB)
        for row in aw.load_servers(DB, sub_id):
            if row['Address'] == addr and str(row['Port']) == str(port):
                con.close()
                return aw.server_name(row['Remarks'])
        con.close()
    except Exception as e:
        log.info('current_node 异常: %s' % e)
    return 'unknown'


def server_row(name):
    rows = [x for x in aw.load_servers(DB, aw.load_sub(DB)[0]) if aw.server_name(x['Remarks']) == name]
    return rows[0] if rows else None


def probe(name):
    row = server_row(name)
    if not row:
        return False, None
    ports = aw.pick_ports(12370, 1, log)
    res = aw.probe_servers([row], XRAY, 12370, 'https://www.google.com/generate_204', 8, log, 'guard')
    r = res[aw.server_name(row['Remarks'])]
    return r['ok'], r.get('latency_ms')


def kill_xray_on_10808():
    """按 10808 监听 inode 精确杀持有者 (防误杀)"""
    try:
        ino = None
        for line in open('/proc/net/tcp').readlines()[1:]:
            p = line.split()
            if p[1] == '0100007F:2A38' and p[3] == '0A':
                ino = p[9]
                break
        if not ino:
            return
        for pidf in glob.glob('/proc/[0-9]*'):
            pid = pidf.split('/')[2]
            try:
                if os.path.exists('/proc/%s/fd' % pid):
                    for fd in glob.glob('/proc/%s/fd/*' % pid):
                        if os.readlink(fd) == 'socket:[%s]' % ino:
                            cmd = open('/proc/%s/cmdline' % pid, 'rb').read().replace(b'\0', b' ').decode('replace')
                            if 'xray' in cmd:
                                os.kill(int(pid), 15)
                                log.info('kill TERM xray pid=%s' % pid)
                                for _ in range(10):
                                    time.sleep(1)
                                    if not os.path.exists('/proc/%s' % pid):
                                        return
                                os.kill(int(pid), 9)
                                log.info('kill KILL xray pid=%s' % pid)
            except Exception:
                pass
    except Exception as e:
        log.info('kill_xray 异常: %s' % e)


def start_xray(row):
    aw.backup(CFG, 5, log)
    cfg = {
        'log': {'loglevel': 'warning'},
        'inbounds': [{
            'tag': 'socks', 'port': 10808, 'listen': '127.0.0.1', 'protocol': 'socks',
            'settings': {'auth': 'noauth', 'udp': True, 'allowTransparent': False},
        }],
        'outbounds': [aw.build_outbound('proxy', row)],
    }
    tmp = CFG + '.tmp'
    json.dump(cfg, open(tmp, 'w'), indent=2, ensure_ascii=False)
    os.replace(tmp, CFG)
    subprocess.Popen([XRAY, 'run', '-c', CFG], cwd=VDIR + '/guiConfigs',
                     stdin=subprocess.DEVNULL,
                     stdout=open('/home/mac/.hermes/logs/v2rayn_fallback_xray.log', 'ab'),
                     stderr=subprocess.STDOUT, start_new_session=True)
    up = aw.wait_port(10808, 15)
    log.info('xray 起 %s: UP=%s' % (aw.server_name(row['Remarks']), up))
    return up


def switch_to(name):
    row = server_row(name)
    if not row:
        return False
    kill_xray_on_10808()
    time.sleep(1)
    if not start_xray(row):
        return False
    return proxy_ok()


def main():
    st = load_state()
    cur = current_node()
    ok = proxy_ok()
    log.info('tick: cur=%s proxy_ok=%s' % (cur, ok))

    # 与每分钟看门狗(v2rayn_proxy_guard.sh, 会跑 run.sh)互斥: 它持 autoswitch.lock
    # 期间它正动 10808, 我们本 tick 让路, 绝不两个同时碰端口 (用户铁律: 不能抢端口)
    def lock_held():
        try:
            import fcntl
            f = open(VDIR + '/autoswitch/autoswitch.lock', 'a')
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.close()
                return False
            except OSError:
                return True
        except Exception:
            return False

    if ok and cur == 'c1s2':
        st['node'] = 'c1s2'
        save_state(st)
        return 0  # 健康, 静默

    if ok and cur != 'c1s2':
        # 当前是兜底(c1s3), 看 c1s2 是否恢复 -> 切回
        if lock_held():
            log.info('autoswitch 持锁, 让路本 tick')
            return 0
        c2_ok, ms = probe('c1s2')
        if c2_ok:
            if switch_to('c1s2'):
                st['node'] = 'c1s2'
                save_state(st)
                notify('v2rayN 已切回 c1s2', 'c1s2 恢复连通 (%s ms), 兜底 xray 已切回 c1s2 并验证 204。\n当前节点: **c1s2**' % ms)
            else:
                log.info('切回 c1s2 验证失败, 保持现状')
        else:
            st['node'] = cur
            save_state(st)
        return 0

    # 代理 FAIL
    if lock_held():
        log.info('autoswitch 持锁, 让路本 tick (端口恢复交给它)')
        return 0
    c2_ok, ms = probe('c1s2')
    if c2_ok:
        # 节点通但 xray 挂了 -> 重启
        if start_xray(server_row('c1s2')) and proxy_ok():
            st['node'] = 'c1s2'
            save_state(st)
            notify('v2rayN 代理已自动恢复', 'xray 核心异常已重启, c1s2 连通 (%s ms), 10808 验证 204。' % ms)
        return 0

    c3_ok, ms3 = probe('c1s3')
    if c3_ok and cur != 'c1s3':
        if switch_to('c1s3'):
            st['node'] = 'c1s3'
            save_state(st)
            notify('v2rayN 已兜底到 c1s3', 'c1s2 断连, 已自动切 **c1s3** 兜底 (%s ms) 并验证 204。\nc1s2 恢复后会自动切回并通知。' % ms3)
        return 0
    if not c3_ok:
        if st.get('node') != 'down':
            notify('v2rayN 告警: c1s2/c1s3 均不可用', 'c1s2 FAIL, c1s3 FAIL。10808 代理当前不可用, 将持续探测, 恢复后自动处理并通知。')
        st['node'] = 'down'
        save_state(st)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log.info('GUARD CRASH: %s' % e)
        try:
            notify('c1s2 守护脚本异常', 'guard 自身出错: %s (已记录日志, 下 tick 继续)' % e)
        except Exception:
            pass
        sys.exit(0)
