#!/usr/bin/env python3
"""deliver_feishu.py — 水木日报直发飞书(绕开 cron live-adapter 投递缺陷 #47056)

用法:
  python deliver_feishu.py <text文件>          # 发 markdown 卡片
  echo "hello" | python deliver_feishu.py -    # 从 stdin
  python deliver_feishu.py --probe "测试文本"   # 发纯文本探测

cron agent 的最终推送步骤改为调用本脚本, 不依赖 auto-delivery
(09-03 08:00/12:00 两次 auto-delivery 均静默失败, gateway 零发送记录).
"""
import json, os, sys, urllib.request

# 路径自适应: Hermes 容器 /opt/data/.env; runner 容器内经宿主挂载 /host-home/.env
ENV_FILE = next(p for p in ("/opt/data/.env", "/host-home/.env",
                            "/home/mac/.hermes/.env") if os.path.exists(p)) \
    if any(os.path.exists(p) for p in ("/opt/data/.env", "/host-home/.env",
                                       "/home/mac/.hermes/.env")) else "/opt/data/.env"
CHAT_ID = "oc_3f03c1c9f05b59bb247d65c90fa1cca1"  # 本 DM 窗口
DOMAIN = "https://open.feishu.cn"


def _creds():
    vals = {}
    try:
        fh = open(ENV_FILE)
    except FileNotFoundError:
        return None, None   # 无 .env (非生产机/不用飞书) -> 优雅降级
    for line in fh:
        line = line.strip()
        if line.startswith("FEISHU_APP_ID="):
            vals["id"] = line.split("=", 1)[1]
        elif line.startswith("FEISHU_APP_SECRET="):
            vals["sec"] = line.split("=", 1)[1]
    return vals.get("id"), vals.get("sec")


def _token(app_id, app_secret):
    req = urllib.request.Request(
        DOMAIN + "/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("tenant_access_token", "")


def send_markdown(md_text):
    """发 markdown 消息(post 类型). 返回 (ok, detail)."""
    app_id, sec = _creds()
    if not app_id or not sec:
        return False, "missing FEISHU_APP_ID/SECRET in %s" % ENV_FILE
    token = _token(app_id, sec)
    if not token:
        return False, "no tenant token"
    # 飞书 post: 按行分段, 每行一个 text 段
    lines = [ln for ln in md_text.split("\n")]
    content = {"zh_cn": {"title": "", "content": [[{"tag": "text", "text": ln}] for ln in lines if ln.strip() != "" or True]}}
    body = {
        "receive_id": CHAT_ID,
        "msg_type": "post",
        "content": json.dumps(content, ensure_ascii=False),
    }
    req = urllib.request.Request(
        DOMAIN + "/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    ok = d.get("code") == 0
    return ok, d.get("msg", "") + " " + d.get("data", {}).get("message_id", "")


def send_text(text):
    app_id, sec = _creds()
    if not app_id or not sec:
        return False, "missing FEISHU_APP_ID/SECRET in %s" % ENV_FILE
    token = _token(app_id, sec)
    if not token:
        return False, "no tenant token"
    body = {"receive_id": CHAT_ID, "msg_type": "text",
            "content": json.dumps({"text": text})}
    req = urllib.request.Request(
        DOMAIN + "/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    ok = d.get("code") == 0
    return ok, d.get("msg", "") + " " + d.get("data", {}).get("message_id", "")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        ok, detail = send_text(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "-":
        ok, detail = send_markdown(sys.stdin.read())
    elif len(sys.argv) >= 2:
        ok, detail = send_markdown(open(sys.argv[1]).read())
    else:
        print("usage: deliver_feishu.py <md_file|-> | --probe <text>")
        sys.exit(2)
    print(("OK " if ok else "FAIL ") + detail)
    sys.exit(0 if ok else 1)
