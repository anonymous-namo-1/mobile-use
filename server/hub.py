"""Mobile Use hub: the Mobile Use app on the phone connects here (over Tailscale) and
local tools send it commands through a Unix socket.

  phone  --TCP, Tailscale IP only, shared key-->  hub  <--/tmp/phone-hub.sock--  MCP server, CLI

Protocol (both sides): one JSON object per line.
  phone -> hub   {"hello": key, "model": ...}, then answers {"id", "ok", "result"|"error"}
  hub -> phone   {"id", "cmd", "args"}
  client -> hub  {"cmd", "args"}            hub -> client  {"ok", "result"|"error"}
"""
import asyncio
import hmac
import itertools
import json
import os
import secrets
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.environ.get("PHONE_HUB_KEY", os.path.join(HERE, "hub.key"))
SOCK = os.environ.get("PHONE_HUB_SOCK", "/tmp/phone-hub.sock")
PORT = int(os.environ.get("PHONE_HUB_PORT", "8765"))
LOCK_FILE = "/tmp/phone-agent.lock"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def key():
    if not os.path.exists(KEY_FILE):
        with open(KEY_FILE, "w") as f:
            f.write(secrets.token_urlsafe(24))
        os.chmod(KEY_FILE, 0o600)
    return open(KEY_FILE).read().strip()


def tailscale_ip():
    ip = os.environ.get("PHONE_HUB_HOST")
    if ip:
        return ip
    out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True).stdout.split()
    if not out:
        raise SystemExit("Tailscale is not up: the hub only listens on the Tailscale address")
    return out[0]


class Hub:
    def __init__(self):
        self.key = key()
        self.phone = None  # (reader, writer, info)
        self.pending = {}
        self.ids = itertools.count(1)
        self.send_lock = asyncio.Lock()

    # ---- phone side ----
    async def on_phone(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            hello = json.loads(await asyncio.wait_for(reader.readline(), 10))
            if not hmac.compare_digest(str(hello.get("hello", "")), self.key):
                log(f"rejected {peer}: wrong key")
                writer.close()
                return
        except Exception as e:
            log(f"rejected {peer}: {e}")
            writer.close()
            return
        if self.phone:
            self.phone[1].close()
        self.phone = (reader, writer, hello)
        log(f"phone connected: {hello.get('model')} from {peer[0]}")
        try:
            while line := await reader.readline():
                msg = json.loads(line)
                fut = self.pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    fut.set_result(msg)
        except Exception as e:
            log(f"phone link error: {e}")
        finally:
            if self.phone and self.phone[1] is writer:
                self.phone = None
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_result({"ok": False, "error": "phone disconnected"})
            self.pending.clear()
            log("phone disconnected")

    async def call(self, cmd, args=None, timeout=60):
        if not self.phone:
            return {"ok": False, "error": "phone not connected (Phone Agent app off, no internet, or Tailscale off on the phone)"}
        rid = next(self.ids)
        fut = asyncio.get_running_loop().create_future()
        self.pending[rid] = fut
        async with self.send_lock:
            w = self.phone[1]
            w.write((json.dumps({"id": rid, "cmd": cmd, "args": args or {}}) + "\n").encode())
            await w.drain()
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.pending.pop(rid, None)
            return {"ok": False, "error": f"phone did not answer {cmd} within {timeout}s"}

    async def keepalive(self):
        while True:
            await asyncio.sleep(25)
            if self.phone:
                r = await self.call("ping", timeout=20)
                if not r.get("ok"):
                    log(f"ping failed: {r.get('error')}")
                    try:
                        self.phone[1].close()
                    except Exception:
                        pass

    # ---- local clients ----
    async def on_client(self, reader, writer):
        try:
            while line := await reader.readline():
                req = json.loads(line)
                if req.get("cmd") == "hub_status":
                    res = {"ok": True, "result": {"connected": bool(self.phone),
                                                  "phone": self.phone[2].get("model") if self.phone else None}}
                else:
                    res = await self.call(req["cmd"], req.get("args"), req.get("timeout", 60))
                writer.write((json.dumps(res) + "\n").encode())
                await writer.drain()
        except Exception as e:
            log(f"client error: {e}")
        finally:
            writer.close()


async def main():
    hub = Hub()
    host = tailscale_ip()
    phone_srv = await asyncio.start_server(hub.on_phone, host, PORT, limit=16 * 1024 * 1024)
    if os.path.exists(SOCK):
        os.remove(SOCK)
    client_srv = await asyncio.start_unix_server(hub.on_client, SOCK, limit=16 * 1024 * 1024)
    os.chmod(SOCK, 0o660)
    try:  # other local agents in the "phonehub" group (e.g. a restricted SSH user for a chat bot) may use the hub
        import grp
        os.chown(SOCK, -1, grp.getgrnam("phonehub").gr_gid)
    except (KeyError, PermissionError):
        pass
    log(f"hub listening for the phone on {host}:{PORT} (Tailscale only), clients on {SOCK}")
    asyncio.create_task(hub.keepalive())
    async with phone_srv, client_srv:
        await asyncio.gather(phone_srv.serve_forever(), client_srv.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
