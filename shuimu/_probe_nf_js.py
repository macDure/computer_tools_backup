import urllib.request, re
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
url="https://static.mysmth.net/nForum/js/pack_b5a4ef7591.js"
req=urllib.request.Request(url, headers={"User-Agent":UA})
try:
    data=urllib.request.urlopen(req, timeout=25).read().decode("utf-8","replace")
except Exception as e:
    print("FETCH ERR", e); raise SystemExit
print("pack.js chars:", len(data))
for kw in ["账号过多","登录的账号","在线","logout","kick","登出","退出","user/exit","user/logout"]:
    idxs=[m.start() for m in re.finditer(re.escape(kw), data)]
    print(f"\n== {kw}: {len(idxs)} hits ==")
    for i in idxs[:4]:
        print("  ..."+data[max(0,i-35):i+45].replace("\n"," ")+"...")
# extract any url-like login/logout endpoints
eps=set(re.findall(r"['\"][^'\"]*(?:login|logout|exit|kick|user)[^'\"]*['\"]", data))
print("\n== candidate endpoint strings ==")
for e in sorted(eps):
    if any(k in e.lower() for k in ["login","logout","exit","kick"]):
        print("  ", e)
print("(end)")
