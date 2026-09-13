#!/usr/bin/env python3
"""单会话诊断探测 (11:00, 锁空闲; 跑完即关, 12:30 前结束)
目的: 回答"惩罚窗口内到底能不能正常访问取数据"
  A. 登录/进版是否正常
  B. 快跳 30 步期间是否出现"行不可解析" — 第一次失败就 dump 整屏 (看它停在哪)
  C. 读 3 篇当前(09-09)的帖 — 证明能真实取到数据
不归档、不记账、不动队列。
"""
import datetime as dt
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS, parse_sel_row, SessionBusy

TZ = dt.timezone(dt.timedelta(hours=8))
def now(): return dt.datetime.now(TZ).strftime('%H:%M:%S')
def log(m):
    line = '[%s] %s' % (now(), m)
    print(line, flush=True)
    with open('/opt/data/scripts/shuimu_daily/logs/diag_probe.log', 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def is_menu(b):
    return any('主选单' in ln for ln in b.screen().split('\n')[:3])

def is_in_board(b):
    return any(('离开[' in ln and '阅读[' in ln) for ln in b.screen().split('\n')[:6])

def dump_screen(b, tag):
    p = '/opt/data/tmp/diag_screen_%s.txt' % tag
    with open(p, 'w', encoding='utf-8') as f:
        f.write(b.screen())
    log('[DUMP] 整屏已存 %s' % p)
    return p

try:
    b = BBS()
except Exception as e:
    log('BBS() init fail: %r' % e); sys.exit(1)

log('[A] 登录 (login_with_retry)...')
try:
    b.login_with_retry()
    log('[A] 登录 OK, 在主选单? %s' % is_menu(b))
except SessionBusy:
    log('SessionBusy — 已有会话, 立即退出'); sys.exit(2)
except Exception as e:
    log('[A] 登录失败: %r' % e); b.close(); sys.exit(1)

log('[B] 进 Stock 版面 (open_board tries=4)...')
try:
    b.open_board('Stock')
    log('[B] open_board 返回; is_in_board=%s' % is_in_board(b))
except Exception as e:
    log('[B] open_board 异常: %r' % e)
    dump_screen(b, 'openfail')
    b.close(); sys.exit(1)
if not is_in_board(b):
    dump_screen(b, 'notinboard')
    b.close(); sys.exit(1)

log('[B] 快跳 30 步 (照抄生产: move_up + recv + 随机停顿), 每次不可解析即 dump 整屏')
unparse_streak = 0
last_row = None
for i in range(1, 31):
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
        log('  step %d: 行不可解析 (streak=%d) → dump' % (i, unparse_streak))
        dump_screen(b, 'step%02d_unparse' % i)
        if unparse_streak >= 3:
            log('  连续 3 次不可解析 — 看 dump 判断卡在哪, 停止快跳')
            break
    else:
        if unparse_streak:
            log('  step %d: 恢复解析 %s' % (i, row[0]))
            unparse_streak = 0
        log('  step %d: id=%s %s %s' % (i, row[0], row[2], (row[3] or '')[:30]))
        last_row = row
    b.move_up()
    b._recv(0.5)
    time.sleep(0.9 + (0.3 if i % 20 == 0 else 0))

if is_menu(b):
    log('[!] 快跳后掉回主选单 = 被踢特征. dump:'); dump_screen(b, 'kicked_to_menu'); b.close(); sys.exit(3)

log('[C] 读 3 篇当前选中的帖 (r 键+翻页), 验证能真实取数')
read_ok = 0
for k in range(3):
    if not is_in_board(b):
        log('  [C%d] 不在版面了, dump:' % (k+1)); dump_screen(b, 'c%d_notinboard' % (k+1)); break
    art = b.read_current_paged(max_pages=5)
    time.sleep(2.0)
    b.back_robust()
    if art and art.get('time_str'):
        read_ok += 1
        log('  [C%d] OK id=%s time=%s title=%s body_len=%d'
            % (k+1, art.get('id'), art.get('time_str'), (art.get('title') or '')[:30], len(art.get('body') or '')))
    else:
        log('  [C%d] 读帖失败/无时间: %r' % (k+1, {kk: (vv[:60] if isinstance(vv,str) else vv) for kk,vv in (art or {}).items()}))
        dump_screen(b, 'c%d_fail' % (k+1))
    time.sleep(3.0)
    b.move_up()
    b._recv(0.5)
    time.sleep(2.0)

b.close()
log('DONE: 快跳结束, 读帖成功 %d/3. 看 diag_screen_*.txt dump 判断卡点' % read_ok)
