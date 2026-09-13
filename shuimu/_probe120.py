#!/usr/bin/env python3
"""09-07 探测: 1次登录 + 120步拟人化快跳, 无踢=PASS 可整段补爬, 否则立即停手
判定与 backfill_range.py 完全一致 (is_in_board 用列表帮助行, 主选单判定看前3行).
被踢判定加 2s 二次确认, 防瞬态渲染误报.
"""
import random, sys, time

sys.path.insert(0, "/opt/data/scripts/shuimu_daily")
from shuimu_telnet import BBS
import shuimu_run as R


def is_in_board(b):
    for ln in b.screen().split("\n")[:6]:
        if "离开[" in ln and "阅读[" in ln:
            return True
    return False


def is_menu(b):
    for ln in b.screen().split("\n")[:3]:
        if "主选单" in ln:
            return True
    return False


def main():
    cfg = R.load_config()
    b = BBS(credentials=cfg["credentials"])
    t0 = time.time()
    b.login_with_retry()
    board = cfg["boards"][0]
    b.open_board(board)
    b._recv(1.5)  # 渲染稳定
    print("PROBE_START board=%s" % board, flush=True)
    if not is_in_board(b):
        print("PROBE_ABORT 进版面后未见列表帮助行 top3=%r" % b.screen().split("\n")[:3], flush=True)
        b.close()
        return
    for i in range(120):
        b.move_up()
        b._recv(0.4)
        if i % 20 == 19:
            time.sleep(random.uniform(1.5, 3.5))
        if not is_in_board(b):
            b._recv(2.0)
            if not is_in_board(b):
                print("PROBE_FAIL step=%d menu=%s top3=%r"
                      % (i + 1, is_menu(b), b.screen().split("\n")[:3]), flush=True)
                break
    else:
        print("PROBE_PASS steps=120 kicks=0 elapsed=%.0fs" % (time.time() - t0), flush=True)
    b.close()


if __name__ == "__main__":
    main()
