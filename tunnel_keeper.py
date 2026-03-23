#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-run two Cloudflare Quick Tunnels (5002 & 6002), restart on exit,
extract trycloudflare URLs, update index.html, and git push.
Absolute-path version; only commits index.html (script itself won't be pushed).
"""

import os, re, sys, time, threading, subprocess, shlex, json
from pathlib import Path
from datetime import datetime

# ====== 绝对路径配置 ======
REPO_DIR = Path("/data/home/yzwang/software/yzwang913.github.io")
INDEX_FILE = REPO_DIR / "index.html"
BRANCH = "main"
CLOUDFLARED_BIN = os.environ.get("CLOUDFLARED", "cloudflared")  # 如需绝对路径，可设环境变量

# 本地端口映射到项目标识：nano=5002, band=6002
PROJECTS = {"nano": 1999, "band": 7002}
LOCAL_URLS = {p: f"http://127.0.0.1:{port}/" for p, port in PROJECTS.items()}
SMART_OVERRIDE_BEGIN = "<!-- AUTO_LOCAL_OVERRIDE_BEGIN -->"
SMART_OVERRIDE_END = "<!-- AUTO_LOCAL_OVERRIDE_END -->"


# 正则：按 data-project="xxx" 就地替换同标签内的 data-url / data-src
RE_LINK_URL = {p: re.compile(rf'(data-project="{p}"[^>]*data-url=")([^"]+)(")', re.I|re.S) for p in PROJECTS}
RE_PREV_SRC = {p: re.compile(rf'(data-project="{p}"[^>]*data-src=")([^"]+)(")', re.I|re.S) for p in PROJECTS}
TRY_URL_RE = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com/?', re.I)

# 可选：首次运行若未设置 git 身份，可用环境变量传入
GIT_NAME = os.environ.get("GIT_NAME", "")
GIT_EMAIL = os.environ.get("GIT_EMAIL", "")

class TunnelRunner(threading.Thread):
    daemon = True
    def __init__(self, project: str, port: int, on_url_found):
        super().__init__(name=f"tunnel-{project}")
        self.project = project
        self.port = port
        self.on_url_found = on_url_found
        self._stop = threading.Event()
        self.current_url = None

    def stop(self): self._stop.set()

    def run(self):
        while not self._stop.is_set():
            cmd = [CLOUDFLARED_BIN, "tunnel", "--url", f"http://127.0.0.1:{self.port}"]
            print(f"[{self.project}] starting: {' '.join(shlex.quote(c) for c in cmd)}", flush=True)
            try:
                with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, bufsize=1) as proc:
                    for line in proc.stdout:
                        line = line.strip()
                        if not line: continue
                        sys.stdout.write(f"[{self.project}] {line}\n"); sys.stdout.flush()
                        m = TRY_URL_RE.search(line)
                        if m:
                            url = m.group(0).rstrip("/") + "/"
                            if url != self.current_url:
                                self.current_url = url
                                self.on_url_found(self.project, url)
                    code = proc.wait()
                    print(f"[{self.project}] cloudflared exited ({code}), restart in 5s...", flush=True)
                    time.sleep(5)
            except FileNotFoundError:
                print(f"[FATAL] cloudflared not found: {CLOUDFLARED_BIN}", file=sys.stderr)
                break
            except Exception as e:
                print(f"[{self.project}] runner error: {e}", file=sys.stderr)
                time.sleep(5)

def git(*args, cwd=REPO_DIR):
    return subprocess.check_output(["git", *args], cwd=str(cwd), text=True).strip()

def ensure_git_identity():
    try:
        name = git("config", "user.name")
        email = git("config", "user.email")
        if name and email: return
    except subprocess.CalledProcessError:
        pass
    if GIT_NAME: git("config", "user.name", GIT_NAME)
    if GIT_EMAIL: git("config", "user.email", GIT_EMAIL)


def build_runtime_override(url_map: dict) -> str:
    payload = {
        proj: {
            "tunnel": (url or ""),
            "local": LOCAL_URLS.get(proj, ""),
        }
        for proj, url in url_map.items()
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return f"""{SMART_OVERRIDE_BEGIN}
<script>
(function(){{
  const cfg = {payload_json};
  const host = (location.hostname || "").toLowerCase();
  const isLocalHost = !host || host === "localhost" || host === "127.0.0.1" || host === "::1" || /^login\d+$/i.test(host);
  const preferLocal = location.protocol === "file:" || isLocalHost;
  Object.entries(cfg).forEach(([project, links]) => {{
    const chosen = (preferLocal && links.local) ? links.local : (links.tunnel || links.local || "");
    if (!chosen) return;
    const link = document.querySelector(`a.gate-link[data-project="${{project}}"]`);
    const preview = document.querySelector(`button.gate-preview[data-project="${{project}}"]`);
    if (link) link.dataset.url = chosen;
    if (preview) preview.dataset.src = chosen;
  }});
}})();
</script>
{SMART_OVERRIDE_END}"""


def update_index_html(url_map: dict) -> bool:
    if not INDEX_FILE.exists():
        print(f"[WARN] index.html not found: {INDEX_FILE}")
        return False
    content = INDEX_FILE.read_text(encoding="utf-8")
    orig = content
    for proj, url in url_map.items():
        if not url:
            continue
        content, n1 = RE_LINK_URL[proj].subn(rf'\1{url}\3', content)
        content, n2 = RE_PREV_SRC[proj].subn(rf'\1{url}\3', content)
        if n1 or n2:
            print(f"[{proj}] index.html updated: data-url({n1}) data-src({n2}) -> {url}")

    block = build_runtime_override(url_map)
    override_re = re.compile(rf"{re.escape(SMART_OVERRIDE_BEGIN)}.*?{re.escape(SMART_OVERRIDE_END)}", re.S)
    if override_re.search(content):
        content = override_re.sub(lambda _m: block, content, count=1)
    elif "</body>" in content:
        content = content.replace("</body>", block + "\n</body>", 1)
    else:
        content += "\n" + block + "\n"

    if content != orig:
        INDEX_FILE.write_text(content, encoding="utf-8")
        return True
    return False

def commit_and_push(msg: str):
    ensure_git_identity()
    try: git("fetch", "origin")
    except subprocess.CalledProcessError: pass
    try: git("rev-parse", "--verify", BRANCH)
    except subprocess.CalledProcessError:
        git("checkout", "-b", BRANCH, f"origin/{BRANCH}")
    else:
        git("checkout", BRANCH)
        try: git("pull", "--ff-only", "origin", BRANCH)
        except subprocess.CalledProcessError: pass

    # 只提交 index.html
    git("add", "index.html")
    # 若 index.html 没变化，commit 会报错；我们捕获并忽略
    try:
        git("commit", "-m", msg)
    except subprocess.CalledProcessError:
        print("[git] nothing to commit (index.html unchanged).")
        return
    print("[git] pushing...")
    git("push", "origin", BRANCH)
    print("[git] push done.")

class Orchestrator:
    def __init__(self):
        self.urls = {k: None for k in PROJECTS}
        self.lock = threading.Lock()

    def on_url_found(self, project, url):
        with self.lock:
            changed = (self.urls.get(project) != url)
            self.urls[project] = url
        if changed:
            print(f"[{project}] new URL: {url}")
            updated = update_index_html(self.urls)
            if updated:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                msg = f"auto: update {project} trycloudflare URL -> {url} ({ts})"
                try:
                    commit_and_push(msg)
                except subprocess.CalledProcessError as e:
                    print(f"[git] error: {e}", file=sys.stderr)

    def run(self):
        if not REPO_DIR.exists():
            print(f"[FATAL] repo dir not found: {REPO_DIR}", file=sys.stderr); sys.exit(1)
        runners = [TunnelRunner(p, port, self.on_url_found) for p, port in PROJECTS.items()]
        for r in runners: r.start()
        try:
            while True: time.sleep(60)
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            for r in runners: r.stop()

def main():
    orch = Orchestrator()
    orch.run()

if __name__ == "__main__":
    main()
