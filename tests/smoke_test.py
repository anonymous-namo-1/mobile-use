"""End-to-end smoke test without a real phone.

Starts the hub on 127.0.0.1 with a temporary key and socket, connects a fake phone that speaks
the same protocol as the Android app, then drives it through the `phone` command and the MCP
server. Run: python tests/smoke_test.py   (needs the server requirements installed)
"""
import asyncio
import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server")
TMP = tempfile.mkdtemp(prefix="mobileuse-test-")
PORT = 18765
ENV = dict(os.environ, PHONE_HUB_HOST="127.0.0.1", PHONE_HUB_PORT=str(PORT),
           PHONE_HUB_SOCK=os.path.join(TMP, "hub.sock"), PHONE_LOCK_FILE=os.path.join(TMP, "lock"),
           PHONE_AGENT_NAME="test-agent", PHONE_HUB_KEY=os.path.join(TMP, "hub.key"))
os.environ.update(ENV)


def tiny_jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (540, 1170), (20, 20, 30)).save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


SCREEN = {"app": "com.example.calculator", "keyboard": False, "locked": False, "screen_on": True,
          "w": 1080, "h": 2340, "els": [
              {"i": 0, "kind": "button", "label": "7", "b": [0, 1300, 270, 1500]},
              {"i": 1, "kind": "button", "label": "Send", "b": [800, 2000, 1080, 2200]},
              {"i": 2, "kind": "field", "label": "Message", "b": [0, 2000, 800, 2200]},
              {"i": 3, "kind": "field", "label": "", "b": [0, 400, 1080, 500], "password": True}]}
calls = []


def fake_phone(key):
    """Answers the hub like the Android app does."""
    s = socket.create_connection(("127.0.0.1", PORT), timeout=10)
    f = s.makefile("rwb")
    f.write((json.dumps({"hello": key, "model": "FakePhone"}) + "\n").encode())
    f.flush()
    for line in f:
        req = json.loads(line)
        cmd, args = req["cmd"], req.get("args", {})
        calls.append((cmd, args))
        if cmd in ("ping", "status"):
            res = {"model": "FakePhone", "screen_on": True, "locked": False, "stopped": False, "app": SCREEN["app"]}
        elif cmd in ("look", "tree"):
            res = dict(SCREEN)
            if cmd == "look" and args.get("shot", True):
                res["jpeg"] = tiny_jpeg()
        elif cmd == "ask":
            res = {"answer": "deny"}  # the owner says no
        elif cmd == "apps":
            res = {"apps": [{"name": "Calculator", "package": "com.example.calculator"}]}
        else:
            res = {"done": cmd}
        f.write((json.dumps({"id": req["id"], "ok": True, "result": res}) + "\n").encode())
        f.flush()


def phone(*args):
    r = subprocess.run([sys.executable, os.path.join(SERVER, "phonectl"), *args],
                       capture_output=True, text=True, env=ENV, timeout=60)
    return r.returncode, (r.stdout + r.stderr).strip()


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        raise SystemExit(1)


def main():
    hub = subprocess.Popen([sys.executable, os.path.join(SERVER, "hub.py")], env=ENV, cwd=TMP,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(1.5)
        key = open(ENV["PHONE_HUB_KEY"]).read().strip()
        import threading
        threading.Thread(target=fake_phone, args=(key,), daemon=True).start()
        time.sleep(0.5)

        # wrong key is rejected
        bad = socket.create_connection(("127.0.0.1", PORT))
        bad.sendall(b'{"hello": "wrong-key"}\n')
        bad.settimeout(5)
        check("hub rejects a wrong key", bad.recv(10) == b"")

        rc, out = phone("status")
        check("phone status", rc == 0 and "FakePhone" in out, out)
        rc, out = phone("look")
        check("phone look lists numbered elements", rc == 0 and "[1] button '7'" in out, out)
        rc, out = phone("click", "1")
        check("phone click", rc == 0 and ("click", {"i": 0}) in calls, out)
        rc, out = phone("click", "2")
        check("Send button needs the owner's Allow (denied here)", rc != 0 and "did not allow" in out, out)
        rc, out = phone("type", "4", "secret")
        check("password field refused", rc != 0 and "password" in out.lower(), out)
        rc, out = phone("open", "calculator")
        check("open app by name", rc == 0 and ("open_app", {"package": "com.example.calculator"}) in calls, out)

        sys.path.insert(0, SERVER)
        import mcp_server

        async def mcp_checks():
            names = [t.name for t in await mcp_server.mcp.list_tools()]
            check("MCP server lists tools", {"look", "tap", "type_text", "ask_owner"} <= set(names), names)
            r = await mcp_server.mcp.call_tool("look", {})
            kinds = [c.type for c in r.content]
            check("MCP look returns text + image", "text" in kinds and "image" in kinds, kinds)
        asyncio.run(mcp_checks())
        print("all checks passed")
    finally:
        hub.terminate()


if __name__ == "__main__":
    main()
