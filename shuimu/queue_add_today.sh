#!/bin/bash
# queue_add_today.sh — 一次性: 把 09-09 丢失的两个主档窗 (08-12, 12-16) 插到补爬队列队首
# 23:52 运行: 当前 runner 23:50 已收手, 00:10 深夜档加载队列, 无竞态
export TZ=Asia/Shanghai
/opt/data/venvs/shuimu/bin/python <<'PYEOF'
import json, os, datetime as dt

p = '/opt/data/scripts/shuimu_daily/backfill_queue.json'
q = json.load(open(p))
have = set((t['day'], t['slot']) for t in q['tasks'])
new = []
for slot, h in (('w08', 8), ('w12', 12)):
    if ('2026-09-09', slot) not in have:
        ws = dt.datetime(2026, 9, 9, h, 0)
        new.append({
            'seq': 0, 'day': '2026-09-09',
            'win_start': ws.isoformat(), 'win_end': (ws + dt.timedelta(hours=4)).isoformat(),
            'slot': slot, 'label': '2026-09-09 %02d:00-%02d:00' % (h, h + 4),
            'status': 'pending', 'posts': None, 'commit': None, 'ts': None, 'attempt': 0,
        })
if new:
    for attempt in range(3):
        q = json.load(open(p))  # 每次重试都重读最新, 避免覆盖并发写入
        have_now = set((t['day'], t['slot']) for t in q['tasks'])
        if ('2026-09-09', 'w08') in have_now and ('2026-09-09', 'w12') in have_now:
            print('QUEUE_PATCH 无需插入 (09-09 w08/w12 已在队列)')
            break
        keep = [t for t in q['tasks'] if (t['day'], t['slot']) != ('2026-09-09', 'w08') and (t['day'], t['slot']) != ('2026-09-09', 'w12')]
        base = new + keep
        for i, t in enumerate(base, 1):
            t['seq'] = i
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(base, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)  # 原子替换, 防止 runner 并发读到半截文件
        # 校验: 重读确认插入仍在 (若被并发 save_queue 覆盖则重试)
        chk = json.load(open(p))
        if any(t['label'] == '2026-09-09 08:00-12:00' for t in chk['tasks']) and \
           any(t['label'] == '2026-09-09 12:00-16:00' for t in chk['tasks']):
            print('QUEUE_PATCH 已插入 %d 窗到队首: %s (队列共 %d)' % (len(new), [t['label'] for t in new], len(chk['tasks'])))
            break
        print('QUEUE_PATCH 校验失败(疑似并发覆盖), 重试 %d' % (attempt + 1))
else:
    print('QUEUE_PATCH 无需插入 (09-09 w08/w12 已在队列)')
PYEOF
