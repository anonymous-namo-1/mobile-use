"""Mobile Use: MCP server (stdio) that lets an AI agent drive the owner's Android phone.

The Mobile Use app on the phone (an accessibility service) connects out to hub.py over
Tailscale. This server talks to the hub through /tmp/phone-hub.sock, so it opens no
network port and needs no ADB. The phone shows a blue glow + a Stop button while active.
"""
import base64
import io
import json
import os
import socket
import threading
import time

import policy
from mcp.server.mcpserver import Image, MCPServer
from PIL import Image as PILImage, ImageDraw, ImageFont

HUB = os.environ.get("PHONE_HUB_SOCK", "/tmp/phone-hub.sock")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "actions.log")
LOCK_FILE = os.environ.get("PHONE_LOCK_FILE", "/tmp/phone-agent.lock")  # shared with other agents (e.g. the `phone` command)
LOCK_SECONDS = 120
SHOT_WIDTH = 540
SETTLE = 0.6  # seconds for the screen to update before looking after an action
ME = f"claude-{os.getpid()}"

mcp = MCPServer("phone", instructions=(
    "Controls the owner's Android phone. Start with look(): screenshot with numbered boxes "
    "and a list like '[7] button \"Send\"'. Act by number: tap(ref=7), type_text('hi', ref=12), "
    "scroll('down'), find('Settings') scrolls until it's visible. Actions return the new screen "
    "(look=false to skip). "
    "Reading the screen, scrolling, opening apps, and typing into ordinary fields just run. "
    "Paying, sending a message, deleting, or installing an app raises a card on the phone: the "
    "owner slides to approve once or for this session, taps Deny, or ignores it and the timer "
    "denies. Pass why= with a short plain reason. If they tap Stop, stop and tell them. "
    "Never type a password, PIN, or one-time code. A password field is refused even if the owner "
    "slides or you pass confirm=true. "
    "Purchases: call set_owner_request with the owner's verbatim request before you shop. "
    "If that request named the app and cash on delivery (COD / pay on delivery), finish the order "
    "end to end, including the final place-order button, with no extra card. Before that tap, "
    "call checkout_status. The payment method on screen must be cash or pay on delivery (an "
    "unchecked option does not count), and the items on screen must be the ones they asked for. "
    "If a card, UPI, or wallet (such as Amazon Pay) is selected, switch it to cash on delivery and "
    "check again. If cash on delivery is not offered, it is unchecked, or the cart has other items, "
    "the place-order tap shows the approval card; do not pay with a prepaid method unless they "
    "approve that card. Any other purchase always needs the card."))

_refs = {}  # number -> element from the latest look()
_front_app = ""
_scale = 2.0  # device px per screenshot px
_apps = None
_lock = threading.Lock()


# ---------- hub ----------

def _hub(cmd, args=None, timeout=60):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout + 5)
    try:
        s.connect(HUB)
    except OSError:
        raise RuntimeError("phone hub is not running (see docs/SETUP.md, step 2)")
    with s:
        s.sendall((json.dumps({"cmd": cmd, "args": args or {}, "timeout": timeout}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
    res = json.loads(buf or b'{"ok": false, "error": "no answer from hub"}')
    if not res.get("ok"):
        raise RuntimeError(res.get("error", "phone error"))
    return res.get("result", {})


# ---------- one driver at a time ----------

def _claim():
    try:
        lock = json.load(open(LOCK_FILE))
        pid = lock["owner"].removeprefix("claude-")
        gone = pid.isdigit() and not os.path.exists(f"/proc/{pid}")
        if lock["owner"] != ME and not gone and time.time() - lock["ts"] < LOCK_SECONDS:
            raise RuntimeError(f"phone busy: {lock['owner']} used it {int(time.time() - lock['ts'])} s ago; "
                               "try again in a bit or ask the owner to stop the other agent")
    except (OSError, ValueError, KeyError):
        pass
    try:
        with open(LOCK_FILE, "w") as f:
            json.dump({"owner": ME, "ts": time.time()}, f)
        os.chmod(LOCK_FILE, 0o666)
    except PermissionError:
        pass


def _log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {ME} {msg}\n")


# ---------- seeing ----------

def _look(shot=True):
    global _refs, _scale, _front_app
    r = _hub("look", {"shot": shot, "width": SHOT_WIDTH})
    _scale = r["w"] / SHOT_WIDTH
    _front_app = r.get("app") or ""
    _refs, lines = {}, []
    img = None
    if shot:
        img = PILImage.open(io.BytesIO(base64.b64decode(r["jpeg"]))).convert("RGB")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default(size=13)
    area = r["w"] * r["h"]
    els = [e for e in r["els"]  # drop screen-sized containers that only repeat all the text below them
           if not (e["kind"] == "button" and len(e["label"]) >= 60
                   and (e["b"][2] - e["b"][0]) * (e["b"][3] - e["b"][1]) > 0.3 * area)]
    for n, e in enumerate(els, 1):
        _refs[n] = e
        x1, y1, x2, y2 = (round(v / _scale) for v in e["b"])
        if img is not None and e["kind"] != "text":
            draw.rectangle((x1, y1, x2, y2), outline=(255, 0, 80), width=2)
            tw = draw.textlength(str(n), font=font)
            draw.rectangle((x1, y1, x1 + tw + 4, y1 + 15), fill=(255, 0, 80))
            draw.text((x1 + 2, y1), str(n), fill="white", font=font)
        flags = "".join([
            " (password: never type)" if e.get("password") else "",
            f" [{'on' if e['checked'] else 'off'}]" if "checked" in e else "",
            " (disabled)" if e.get("disabled") else "",
            " (selected)" if e.get("selected") else ""])
        name = repr(e["label"]) if e["label"] else f"id={e.get('id', '?')}"
        lines.append(f"[{n}] {e['kind']} {name} at {(x1 + x2) // 2},{(y1 + y2) // 2}{flags}")
    head = f"app: {r['app']}" + (" | keyboard open" if r.get("keyboard") else "") \
        + (" | PHONE LOCKED: ask the owner to unlock it (never type the PIN)" if r.get("locked") else "") \
        + ("" if r.get("screen_on", True) else " | screen off (call wake)")
    text = head + "\n" + "\n".join(lines)
    if img is None:
        return text
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return [text, Image(data=buf.getvalue(), format="jpeg")]


def _after(msg, look):
    _log(msg)
    if not look:
        return msg
    time.sleep(SETTLE)
    res = _look()
    return [msg + "\n" + res[0], res[1]]


def _el(ref):
    if ref not in _refs:
        raise ValueError(f"no element [{ref}] in the last look(); call look() again")
    return _refs[ref]


def _hub_call(cmd, args=None, timeout=60):
    try:
        return _hub(cmd, args, timeout)
    except RuntimeError as err:
        if "stopped" in str(err):
            policy.get_store().clear_session()
        raise


def _guard(ref=0, confirm=False, what="", kind="tap", enter=False, typed=""):
    """Harmless actions pass. Risky ones wait for the slide card. See policy.py."""
    _claim()
    try:
        return policy.authorize(
            _hub_call, kind=kind, element=_refs.get(ref) if ref else None,
            elements=list(_refs.values()), why=what, confirm=confirm, enter=enter,
            agent=ME, typed=typed, seen_app=_front_app)
    except policy.ApprovalDenied as err:
        raise PermissionError(str(err)) from None


# ---------- tools ----------

@mcp.tool()
def status() -> str:
    """Is the phone connected? Shows model, app in front, locked / screen off / stopped."""
    hub = _hub("hub_status")
    if not hub.get("connected"):
        return ("phone NOT connected. On the phone: Tailscale on, Mobile Use switched on in "
                "Settings > Accessibility, internet working.")
    return json.dumps(_hub("ping"))  # ping also works while the owner has pressed Stop


@mcp.tool()
def look():
    """See the phone: screenshot with numbered boxes + list of buttons, fields and text.
    Use the numbers with tap / type_text."""
    with _lock:
        return _look()


@mcp.tool()
def read_screen() -> str:
    """Only the numbered list of what's on screen, no image (fastest, least data)."""
    with _lock:
        return _look(shot=False)


@mcp.tool()
def screenshot() -> Image:
    """Just the screen image, no list."""
    r = _hub("screenshot", {"width": SHOT_WIDTH})
    return Image(data=base64.b64decode(r["jpeg"]), format="jpeg")


@mcp.tool()
def tap(ref: int = 0, x: int = -1, y: int = -1, confirm: bool = False, look: bool = True, why: str = ""):
    """Tap element [ref] from the last look(), or (x, y) in screenshot pixels.
    why: plain reason shown on the approval card when this tap is risky."""
    with _lock:
        decision = _guard(ref, confirm, why, kind="tap")
        if ref:
            e = _el(ref)
            _hub("click", {"i": e["i"], "approved": bool(decision.get("approved"))})
            what = f"tapped [{ref}] {e['label']!r}"
        else:
            _hub("tap", {"x": round(x * _scale), "y": round(y * _scale)})
            what = f"tapped {x},{y}"
        if decision.get("auto_cod"):
            what += " (cash-on-delivery order placed and logged)"
        return _after(what, look)


@mcp.tool()
def long_press(ref: int = 0, x: int = -1, y: int = -1, confirm: bool = False, look: bool = True, why: str = ""):
    """Long-press element [ref] or (x, y) in screenshot pixels."""
    with _lock:
        decision = _guard(ref, confirm, why, kind="long_press")
        if ref:
            _hub("long_click", {"i": _el(ref)["i"], "approved": bool(decision.get("approved"))})
        else:
            _hub("long_tap", {"x": round(x * _scale), "y": round(y * _scale)})
        return _after(f"long-pressed {ref or (x, y)}", look)


@mcp.tool()
def type_text(text: str, ref: int = 0, clear: bool = True, enter: bool = False,
              confirm: bool = False, look: bool = True, why: str = ""):
    """Type text (any language, emoji OK) into field [ref], or the focused field if ref=0.
    clear=false appends; enter=true presses the keyboard's Enter/Search/Send key afterwards
    (that needs approval, because it can send a message)."""
    with _lock:
        decision = _guard(ref, confirm, why, kind="type", enter=enter, typed=text)
        args = {"text": text, "clear": clear, "enter": enter, "approved": bool(decision.get("approved"))}
        if ref:
            args["i"] = _el(ref)["i"]
        _hub("set_text", args)
        return _after(f"typed {len(text)} characters" + (f" into [{ref}]" if ref else ""), look)


@mcp.tool()
def scroll(direction: str = "down", look: bool = True):
    """Scroll: down (see more below), up, left, right."""
    with _lock:
        _claim()
        w = round(SHOT_WIDTH * _scale)
        h = round(w * 2340 / 1080) if not _refs else max(e["b"][3] for e in _refs.values())
        cx, cy = w // 2, h // 2
        moves = {"down": (cx, int(h * .72), cx, int(h * .32)), "up": (cx, int(h * .32), cx, int(h * .72)),
                 "left": (int(w * .85), cy, int(w * .15), cy), "right": (int(w * .15), cy, int(w * .85), cy)}
        if direction not in moves:
            raise ValueError("direction must be down, up, left or right")
        x1, y1, x2, y2 = moves[direction]
        _hub("swipe", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "ms": 280})
        return _after(f"scrolled {direction}", look)


@mcp.tool()
def swipe(x1: int, y1: int, x2: int, y2: int, ms: int = 300, look: bool = True):
    """Swipe from (x1, y1) to (x2, y2) in screenshot pixels."""
    with _lock:
        _claim()
        s = _scale
        _hub("swipe", {"x1": round(x1 * s), "y1": round(y1 * s), "x2": round(x2 * s), "y2": round(y2 * s), "ms": ms})
        return _after("swiped", look)


@mcp.tool()
def press_key(key: str, look: bool = True):
    """Press: back, home, recent, notifications, quick_settings."""
    if key not in ("back", "home", "recent", "notifications", "quick_settings"):
        raise ValueError("key must be back, home, recent, notifications or quick_settings")
    with _lock:
        _claim()
        _hub("global", {"key": key})
        return _after(f"pressed {key}", look)


def _app_list():
    global _apps
    if _apps is None:
        _apps = _hub("apps")["apps"]
    return _apps


@mcp.tool()
def open_app(name: str, look: bool = True):
    """Open an app by its name or package, e.g. "WhatsApp", "Amazon", "com.whatsapp"."""
    with _lock:
        _claim()
        key = name.lower().strip()
        apps = _app_list()
        hits = [a for a in apps if a["package"] == name or a["name"].lower() == key] \
            or [a for a in apps if key in a["name"].lower()] \
            or [a for a in apps if key.replace(" ", "") in a["package"].lower()]
        if not hits:
            raise ValueError(f"no app called {name!r}; see list_apps")
        app = sorted(hits, key=lambda a: len(a["name"]))[0]
        _hub("open_app", {"package": app["package"]}, timeout=20)
        others = ", ".join(a["name"] for a in hits[1:4])
        return _after(f"opened {app['name']} ({app['package']})" + (f"; also matched: {others}" if others else ""), look)


@mcp.tool()
def list_apps(filter: str = "") -> str:
    """Installed apps (name and package), optionally filtered."""
    global _apps
    _apps = None
    return "\n".join(f"{a['name']}: {a['package']}" for a in sorted(_app_list(), key=lambda a: a["name"].lower())
                     if filter.lower() in (a["name"] + a["package"]).lower())


@mcp.tool()
def wait_for(text: str, timeout: int = 15, look: bool = True):
    """Wait until text appears on screen (checked on the phone every 0.25 s)."""
    with _lock:
        r = _hub("wait_for", {"text": text, "timeout": timeout}, timeout=timeout + 10)
        msg = f"{text!r} {'appeared' if r.get('found') else 'did not appear'} within {timeout}s"
        return _after(msg, look) if r.get("found") else msg


@mcp.tool()
def find(text: str, max_scrolls: int = 8, look: bool = True):
    """Scroll down the screen's list until text is visible (e.g. a setting or contact)."""
    with _lock:
        _claim()
        r = _hub("find", {"text": text, "max_scrolls": max_scrolls}, timeout=60)
        msg = f"{text!r} {'found' if r.get('found') else 'not found'} after {r.get('scrolls')} scrolls"
        return _after(msg, look)


@mcp.tool()
def ask_owner(question: str, timeout: int = 60) -> str:
    """Show the approval card on the phone and wait. Returns allow_once, allow_session, deny, or timeout."""
    r = _hub("ask", {"title": "Question", "text": question, "why": "The agent is asking you to decide.",
                     "risk": "question", "timeout": timeout}, timeout=timeout + 15)
    answer = r.get("answer", "timeout")
    policy.get_store().audit("approval", agent=ME, decision=answer, risk="question", action=question[:160])
    _log(f"asked owner: {question!r} -> {answer}")
    return answer


@mcp.tool()
def set_owner_request(text: str) -> str:
    """Record the owner's verbatim request. Arms cash-on-delivery auto-complete only when the
    text names an installed shopping app and cash on delivery (COD / pay on delivery)."""
    apps = _hub("apps").get("apps", [])
    rec = policy.get_store().save_request(text, apps)
    return policy.explain_request(rec)


@mcp.tool()
def checkout_status() -> str:
    """Read the checkout screen: which payment method is selected, the total, and whether
    the final place-order tap will auto-complete, ask to switch to cash on delivery, or raise the card."""
    with _lock:
        _claim()
        _look(shot=False)
        return policy.explain_checkout(_front_app, list(_refs.values()))


@mcp.tool()
def approval_log(limit: int = 20) -> str:
    """Recent approval decisions and cash-on-delivery orders (app, items, total, time)."""
    return policy.format_audit(policy.get_store().read_audit(limit))


@mcp.tool()
def set_policy(cod_auto_complete: bool) -> str:
    """Turn the cash-on-delivery auto-complete rule on or off. It is on by default."""
    cfg = policy.set_cod_auto_complete(cod_auto_complete)
    state = "on" if cfg["cod_auto_complete"] else "off"
    policy.get_store().audit("policy", agent=ME, decision=state, action="cod_auto_complete")
    return f"cod_auto_complete is {state}"


@mcp.tool()
def revoke_approvals() -> str:
    """Clear 'approve for this session' grants. The next risky action asks on the phone again."""
    policy.get_store().clear_session()
    return "session approvals cleared"


@mcp.tool()
def wake(look: bool = True):
    """Turn the screen on (it won't unlock a locked phone)."""
    with _lock:
        _claim()
        _hub("wake")
        return _after("woke the screen", look)


if __name__ == "__main__":
    mcp.run("stdio")
