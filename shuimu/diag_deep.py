#!/usr/bin/env python3
"""深跳诊断 (11:03~11:15, 单会话, 不碰 12:00 主档/12:30 补爬)
照抄 backfill_window 生产快跳节奏, 深跳 ~130 步到 09-08 区域 (10:30 那轮死在 101 步后)
第一次行不可解析即 dump 整屏; 连续 5 次 dump 5 张并停。
"""
import datetime as dt
import os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS, parse_sel_row, SessionBusy

TZ = dt.timezone(dt.timedelta(hours=8))
def now(): return dt.datetime.now(TZ).strftime('%H:%M:%S')
def log(m):
    line = '[%s] %s' % (now(), m)
    print(line, flush=True)
    with open('/opt/data/scripts/shuimu_daily/logs/diag_deep.log', 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def is_in_board(b):
    return any(('离开[' in ln and '阅读[' in ln) for ln in b.screen().split('\n')[:6])

def is_menu(b):
    return any('主选单' in ln for ln in b.screen().split('\n')[:3])

def dump_screen(b, tag):
    p = '/opt/data/tmp/deep_%s.txt' % tag
    with open(p, 'w', encoding='utf-8') as f:
        f.write(b.screen())
    log('  [DUMP] %s' % p)
    return p

b = BBS()
log('登录...')
try:
    b.login_with_retry()
except SessionBusy:
    log('SessionBusy 退出'); sys.exit(2)
log('进 Stock...')
b.open_board('Stock')
if not is_in_board(b):
    dump_screen(b, 'notinboard'); b.close(); sys.exit(1)
log('开始深跳 (生产节奏: move_up + _recv(0.5) + uniform(1.5,3.5), 每20步歇1.5s)')

unparse_streak = 0
dumps = 0
t0 = time.time()
for i in range(1, 131):
    scr = b.screen()
    row = None
    for ln in scr.split('\n'):
        if not ln.strip(): continue
        if ln.strip().startswith('[提示]'): continue
        r = parse_sel_row(ln, year=2026)
        if r:
            row = r; break
    if row is None:
        unparse_streak += 1
        log('  step %d: 不可解析 streak=%d' % (i, unparse_streak))
        dump_screen(b, 'step%03d_s%d' % (i, unparse_streak))
        dumps += 1
        if unparse_streak >= 5 or dumps >= 6:
            log('  连续不可解析确认, 停止. 总耗时 %.0fs' % (time.time()-t0))
            break
        b._recv(1.2)
        continue
    if unparse_streak:
        log('  step %d: 恢复 (此前 streak=%d)' % (i, unparse_streak))
        unparse_streak = 0
    if i % 10 == 0 or row[2] not in (None,):
        pass
    if i % 20 == 0:
        log('  step %d: id=%s date=%s %s' % (i, row[0], row[2], (row[3] or '')[:28]))
        time.sleep(1.5)
    b.move_up()
    b._recv(0.5)
    time.sleep(random.uniform(1.5, 3.5))

log('结束: 最终日期=%s 耗时 %.0fs 不可解析streak峰值未记录但 dumps=%d' % (
    (row[2] if row else '?'), time.time()-t0, dumps))
if is_menu(b):
    log('[!] 掉回主选单=被踢'); dump_screen(b, 'kicked')
b.close()
log('DONE')
