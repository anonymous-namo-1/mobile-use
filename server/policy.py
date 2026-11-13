"""Risk tiers, the on-phone approval card, and the cash-on-delivery purchase rule.

Harmless actions (reading the screen, scrolling, opening an app, typing into an ordinary
field) run with no prompt. Risky ones raise a card on the phone. The owner slides to
approve once or for this session; Deny or the timer refuses.

cod_auto_complete (policy.json, on by default; override in policy.local.json or with
PHONE_COD_AUTO_COMPLETE) lets the agent finish an order without that card only when ALL
of these are true:

  - the owner's own request named the shopping app and cash / pay on delivery (or COD)
  - the app in front is that app, and it is not a payment/banking app
  - the checkout screen really shows cash / pay on delivery as the payment method
  - an option marked unchecked is not treated as selected
  - every product line on screen matches the items in that request

A card, UPI, or wallet (including Amazon Pay) is never auto-completed. If cash on
delivery is on the screen but not selected, the tap is refused with instructions to
switch. If it is not offered, or the cart has anything else in it, the normal approval
card is shown. Password and PIN fields are never typed into.
"""
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))

SENSITIVE_RE = re.compile(
    r"pay|bank|upi|wallet|paisa|phonepe|paytm|nbu|sbi|icici|hdfc|axis|kotak|"
    r"zerodha|groww|upstox|binance|coin|crypto|stripe|razorpay", re.I)
INSTALL_RE = re.compile(r"^(install|install now|install app)\b", re.I)
DELETE_RE = re.compile(
    r"^(delete|remove|uninstall|erase|clear chat|unsubscribe|cancel subscription)\b", re.I)
MESSAGE_RE = re.compile(r"^(send|send message|post|publish|reply|share)\b", re.I)
CONFIRM_RE = re.compile(r"^(confirm|submit)\b", re.I)
FINAL_RE = re.compile(
    r"^(place order|place your order|place the order|confirm order|confirm purchase)\b", re.I)
PAY_RE = re.compile(r"^(pay|pay now|pay online|proceed to pay|make payment|transfer)\b", re.I)
BUY_RE = re.compile(r"^(buy now|buy|order now)\b", re.I)
NAV_RE = re.compile(
    r"^(checkout|proceed to checkout|go to cart|view cart|add to cart|"
    r"choose address|select address|deliver here|confirm address|confirm location|"
    r"change address|use this address|deliver to this address)\b", re.I)
SEARCH_RE = re.compile(r"\b(search|find)\b", re.I)
COD_PHRASE_RE = re.compile(
    r"\b(cash on delivery|pay on delivery|payment on delivery|cash on pickup|pay on receipt)\b", re.I)
COD_SHORT_RE = re.compile(r"^(cod|c\.o\.d\.?)$", re.I)
COD_REQUEST_RE = re.compile(
    r"(cash on delivery|pay on delivery|payment on delivery|cash on pickup|pay on receipt|\bcod\b)", re.I)
PREPAID_RE = re.compile(
    r"\b(upi|credit card|debit card|visa|mastercard|master card|rupay|amex|american express|"
    r"net ?banking|amazon pay|paytm|phonepe|gpay|google pay|prepaid|pay online|"
    r"wallet balance|mobikwik|freecharge|sodexo|simpl|lazypay|lazy pay|pay later|"
    r"card ending|debit|credit)\b", re.I)
OFFER_RE = re.compile(r"\b(available|eligible|accepted here)\b", re.I)
CHOSEN_RE = re.compile(r"\b(selected|currently selected)\b", re.I)
MONEY_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.\d{1,2})?)")
TOTAL_RE = re.compile(r"\b(grand total|to pay|order total|total|amount payable|you pay|bill total)\b", re.I)
ITEM_RE = re.compile(r"\b(?:order|buy|get|purchase)\s+(.+?)\s+(?:on|from|via|using|in)\b", re.I)

# App names that show up inside ordinary sentences and must not arm the purchase rule.
_NAME_STOPWORDS = {
    "on", "and", "the", "app", "for", "pay", "cod", "cash", "order", "buy", "get", "from",
    "with", "via", "delivery", "phone", "android", "google", "play", "store", "please",
    "using", "use", "paid", "payment", "method", "item", "items", "cart", "checkout",
}

_TITLES = {
    "payment": "Payment",
    "message": "Message",
    "delete": "Delete",
    "install": "Install",
    "password": "Password",
    "confirm": "Confirm",
    "question": "Question",
}
_CONSEQUENCE = {
    "payment": "This can spend money or place an order.",
    "message": "This sends a message or post from your phone.",
    "delete": "This can delete something.",
    "install": "This installs an app on your phone.",
    "password": "This types into a password or PIN field.",
    "confirm": "This confirms something that may be hard to undo.",
    "question": "The agent is asking you to decide.",
}
_DEFAULTS = {"cod_auto_complete": True, "approval_timeout_sec": 60, "session_minutes": 30}


class ApprovalDenied(Exception):
    """The owner did not approve, or a purchase must change payment method first."""


def _policy_path():
    return os.environ.get("PHONE_POLICY_FILE", os.path.join(HERE, "policy.json"))


def _local_path():
    return os.environ.get("PHONE_POLICY_LOCAL", os.path.join(HERE, "policy.local.json"))


def load_policy():
    cfg = dict(_DEFAULTS)
    for path in (_policy_path(), _local_path()):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, ValueError):
            pass
    env = os.environ.get("PHONE_COD_AUTO_COMPLETE")
    if env is not None and env.strip() != "":
        cfg["cod_auto_complete"] = env.strip().lower() in ("1", "true", "yes", "on")
    cfg["cod_auto_complete"] = bool(cfg.get("cod_auto_complete", True))
    try:
        cfg["approval_timeout_sec"] = int(cfg.get("approval_timeout_sec") or 60)
    except (TypeError, ValueError):
        cfg["approval_timeout_sec"] = 60
    try:
        cfg["session_minutes"] = int(cfg.get("session_minutes") or 30)
    except (TypeError, ValueError):
        cfg["session_minutes"] = 30
    return cfg


def set_cod_auto_complete(enabled):
    path = _local_path()
    cur = {}
    try:
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
        if not isinstance(cur, dict):
            cur = {}
    except (OSError, ValueError):
        cur = {}
    cur["cod_auto_complete"] = bool(enabled)
    _write_json(path, cur)
    return load_policy()


def _write_json(path, obj):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass


class Store:
    """Session grants, the owner's current request, and the audit log."""

    def __init__(self):
        self.session_path = os.environ.get("PHONE_SESSION_FILE", "/tmp/phone-session-grants.json")
        self.request_path = os.environ.get("PHONE_OWNER_REQUEST", "/tmp/phone-owner-request.json")
        self.audit_path = os.environ.get("PHONE_AUDIT_LOG", os.path.join(HERE, "audit.log"))

    def audit(self, event, **fields):
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event}
        rec.update({k: v for k, v in fields.items() if v is not None})
        parent = os.path.dirname(self.audit_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        try:
            os.chmod(self.audit_path, 0o666)
        except OSError:
            pass
        return rec

    def read_audit(self, limit=20):
        try:
            lines = open(self.audit_path, encoding="utf-8").read().splitlines()
        except OSError:
            return []
        out = []
        for line in lines[-max(1, limit):]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def _grants(self):
        try:
            with open(self.session_path, encoding="utf-8") as f:
                data = json.load(f)
            grants = data.get("grants", []) if isinstance(data, dict) else []
        except (OSError, ValueError):
            grants = []
        now = time.time()
        return [g for g in grants if g.get("until", 0) > now]

    def allows(self, risk, app):
        return any(g.get("risk") == risk and g.get("app") == (app or "") for g in self._grants())

    def grant(self, risk, app, minutes, agent):
        grants = self._grants()
        grants.append({
            "risk": risk, "app": app or "", "agent": agent,
            "until": time.time() + max(1, minutes) * 60,
        })
        _write_json(self.session_path, {"grants": grants})

    def clear_session(self):
        try:
            os.remove(self.session_path)
        except OSError:
            pass

    def save_request(self, text, apps):
        matched = match_apps(text, apps)
        cod = bool(COD_REQUEST_RE.search(text or ""))
        rec = {
            "text": text or "",
            "cod": cod,
            "armed": bool(cod and matched),
            "names": [a["name"] for a in matched],
            "packages": [a["package"] for a in matched],
            "ts": time.time(),
        }
        _write_json(self.request_path, rec)
        return rec

    def request(self):
        try:
            with open(self.request_path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            return {}
        if not isinstance(rec, dict):
            return {}
        minutes = load_policy()["session_minutes"]
        if time.time() - float(rec.get("ts") or 0) > minutes * 60:
            return {}
        return rec


def get_store():
    return Store()


def sensitive(value):
    return bool(value and SENSITIVE_RE.search(value))


def is_cod_label(label):
    text = label or ""
    if COD_PHRASE_RE.search(text):
        return True
    return COD_SHORT_RE.match(text.strip()) is not None


def is_final(label):
    return FINAL_RE.search(label or "") is not None


def is_explicit_pay(label):
    return PAY_RE.search(label or "") is not None and not is_cod_label(label)


def is_buy_now(label):
    return BUY_RE.search(label or "") is not None


def is_navigation(label):
    return NAV_RE.search(label or "") is not None


def classify(kind, element=None, app="", enter=False):
    """A risk name, or None when the action is harmless and needs no card."""
    label = (element or {}).get("label") or ""
    if element and element.get("password"):
        return "password"
    if kind not in ("tap", "long_press", "type"):
        return None
    if INSTALL_RE.search(label):
        return "install"
    if DELETE_RE.search(label):
        return "delete"
    if MESSAGE_RE.search(label):
        return "message"
    if is_final(label) or is_explicit_pay(label) or is_buy_now(label) or (
            is_navigation(label) and re.match(r"^checkout\b", label or "", re.I)):
        return "payment"
    if CONFIRM_RE.search(label):
        return "confirm"
    if kind == "type" and enter and not SEARCH_RE.search(label):
        return "message"
    if sensitive(app) and kind in ("tap", "long_press", "type"):
        return "payment"
    return None


def match_apps(text, apps):
    """Installed apps whose name (or package) is written in the owner's request."""
    found, seen = [], set()
    for raw in apps or []:
        name = (raw.get("name") or "").strip()
        pkg = (raw.get("package") or "").strip()
        key = pkg or name
        if not key or key in seen:
            continue
        if sensitive(pkg) or sensitive(name):
            continue
        name_l = name.lower()
        name_ok = (len(name_l) >= 3 and name_l not in _NAME_STOPWORDS
                   and re.search(r"\b" + re.escape(name) + r"\b", text or "", re.I))
        pkg_ok = bool(pkg) and re.search(r"\b" + re.escape(pkg) + r"\b", text or "", re.I)
        if name_ok or pkg_ok:
            seen.add(key)
            found.append({"name": name, "package": pkg})
    return found


def request_covers(req, app):
    if not req or not req.get("armed") or not app:
        return False
    if app in (req.get("packages") or []):
        return True
    flat = app.lower().replace(".", "")
    for name in req.get("names") or []:
        token = re.sub(r"[^a-z0-9]", "", name.lower())
        if len(token) >= 4 and token in flat:
            return True
    return False


def _explicit_off(element):
    """True when the tree says this control is off, not merely silent about it."""
    if "checked" in element and not element.get("checked"):
        return True
    if "selected" in element and element.get("selected") is False:
        return True
    return False


def _chosen(element, label):
    if _explicit_off(element):
        return False
    if element.get("checked") or element.get("selected"):
        return True
    return CHOSEN_RE.search(label or "") is not None


def _offer_only(label):
    """A badge such as 'Cash on delivery available' is not the method in force."""
    return OFFER_RE.search(label or "") is not None


def payment_state(elements):
    """How checkout is set to be paid.

    cod_selected     cash / pay on delivery is the method in force
    cod_unselected   it is on screen, but not the method in force
    cod_unavailable  only prepaid methods are on screen
    unknown          no payment method is visible (a bare 'available' badge does not count)
    """
    cod_chosen = cod_bare = cod_any = False
    pre_chosen = pre_any = False
    for e in elements or []:
        label = e.get("label") or ""
        if not label:
            continue
        chosen = _chosen(e, label)
        if is_cod_label(label):
            cod_any = True
            # checked:false is not "the method in force", even when no prepaid row is present.
            if not _explicit_off(e):
                cod_chosen = cod_chosen or chosen
                if chosen or not _offer_only(label):
                    cod_bare = True
        elif PREPAID_RE.search(label):
            pre_any = True
            pre_chosen = pre_chosen or chosen
    if cod_chosen and not pre_chosen:
        return "cod_selected"
    if cod_bare and not pre_any:
        return "cod_selected"
    if cod_any and (cod_bare or pre_any or cod_chosen):
        return "cod_unselected"
    if pre_any:
        return "cod_unavailable"
    return "unknown"


def purchase_gate(cfg, req, app, label, elements, element=None):
    """What the COD rule says about this tap.

    None       the rule does not apply; use the normal risk tier
    navigate   part of finishing the COD order (cart, checkout, choosing COD)
    auto       place the order now and write the audit log
    switch     prepaid is selected and COD is on screen; do not tap
    card       COD is not available, or it could not be verified; show the card
    """
    if not cfg.get("cod_auto_complete", True):
        return None
    if sensitive(app) or not request_covers(req, app):
        return None
    label = (label or "").strip()
    if not label:
        return None
    kind = (element or {}).get("kind")
    if is_cod_label(label) and not is_final(label):
        others = [e for e in (elements or []) if e is not element]
        only_finish = kind == "button" and not any(
            is_final(e.get("label") or "") or is_explicit_pay(e.get("label") or "") for e in others)
        if only_finish and payment_state(elements) in ("cod_selected", "unknown"):
            return _finish(req, elements)
        return "navigate"
    if is_navigation(label) and not is_final(label) and not is_explicit_pay(label):
        return "navigate"
    if not (is_final(label) or is_explicit_pay(label) or is_buy_now(label)):
        return None
    state = payment_state(elements)
    # "Buy now" on a product page has no payment method yet: keep going.
    # Once a method is visible, it is the completing tap and follows the same rules.
    if is_buy_now(label) and not is_final(label) and not is_explicit_pay(label) and state == "unknown":
        return "navigate"
    if state == "cod_selected":
        return _finish(req, elements)
    if state == "cod_unselected":
        return "switch"
    return "card"


def prepaid_labels(elements):
    out = []
    for e in elements or []:
        label = (e.get("label") or "").strip()
        if not label or is_cod_label(label) or not PREPAID_RE.search(label):
            continue
        mark = " (selected)" if _chosen(e, label) else ""
        text = (label[:60] + mark).strip()
        if text not in out:
            out.append(text)
    return out


def switch_message(elements):
    seen = ", ".join(prepaid_labels(elements)[:3]) or "a prepaid method"
    return (
        f"Checkout is not cash on delivery (seeing: {seen}). "
        "Switch the payment method to Cash on delivery or Pay on delivery, then place the order again. "
        "Do not pay with a card, UPI, or wallet."
    )


_CHROME_RE = re.compile(
    r"\b(total|to pay|delivery fee|handling fee|handling charge|platform fee|gst|"
    r"tax|taxes|tip|coupon|bill details|item total|grand total|packaging|surge|"
    r"donation|cutlery|delivery in|minutes|address|deliver to|order summary|"
    r"savings|discount|view details|quantity|you pay|amount payable|free delivery|"
    r"delivery charge|saved address)\b", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+")
_ITEM_STOP = {
    "a", "an", "the", "of", "and", "with", "some", "pack", "pcs", "pc", "kg", "ml",
    "ltr", "for", "from", "via", "using", "cash", "delivery", "pay", "cod",
}


def cart_lines(elements):
    """Product-like labels on the checkout screen, not payment rows or bill chrome."""
    lines = []
    for e in elements or []:
        label = (e.get("label") or "").strip()
        if not (3 <= len(label) <= 80) or not re.search(r"[A-Za-z]", label):
            continue
        if (is_cod_label(label) or is_final(label) or is_explicit_pay(label)
                or is_navigation(label) or is_buy_now(label) or PREPAID_RE.search(label)
                or _CHROME_RE.search(label)):
            continue
        if e.get("kind") == "button" and re.match(
                r"^(add|remove|delete|change|edit|apply|view|see|hide|ok|cancel|done|close|back)\b",
                label, re.I):
            continue
        if label not in lines:
            lines.append(label)
    return lines[:8]


def _item_tokens(text):
    return [w for w in _WORD_RE.findall((text or "").lower()) if len(w) >= 3 and w not in _ITEM_STOP]


def cart_problem(req, elements):
    """None when every visible product line is part of the owner's request.

    Otherwise a sentence for the approval card. A cart we cannot see, or one that
    contains something else, is not auto-completed.
    """
    requested = extract_items((req or {}).get("text") or "")
    tokens = _item_tokens(requested)
    lines = cart_lines(elements)
    if not tokens:
        return "The request does not name the items, so this order needs your approval."
    if not lines:
        return "The cart items are not on this screen, so this order needs your approval."
    extras = [line for line in lines if not any(tok in line.lower() for tok in tokens)]
    if extras:
        shown = ", ".join(extras[:3])
        return f"The cart has items that were not requested ({shown}). Approve only if that cart is right."
    return None


def _finish(req, elements):
    """Place the order only when the visible cart is exactly the requested items."""
    if cart_problem(req, elements):
        return "card"
    return "auto"


def extract_items(text):
    m = ITEM_RE.search(text or "")
    if not m:
        return ""
    items = m.group(1).strip(" .,!?:;\"'")
    items = re.sub(r"^(some|the|a|an)\s+", "", items, flags=re.I)
    return items[:120]


def screen_total(elements):
    fallback = ""
    for e in elements or []:
        label = e.get("label") or ""
        m = MONEY_RE.search(label)
        if not m:
            continue
        amount = "₹" + m.group(1)
        if TOTAL_RE.search(label):
            return amount
        fallback = amount
    return fallback


def _app_label(req, package):
    for name, pkg in zip(req.get("names") or [], req.get("packages") or []):
        if pkg == package:
            return name or package
    names = req.get("names") or []
    return names[0] if names else (package or "")


def order_fields(req, app, elements, label):
    seen = cart_lines(elements)
    return {
        "app": _app_label(req, app),
        "package": app,
        "items": "; ".join(seen) if seen else "not shown",
        "requested": extract_items(req.get("text") or "") or "not shown",
        "total": screen_total(elements) or "not shown",
        "button": label,
        "request": req.get("text") or "",
    }


def describe(risk, kind, element, why, typed=""):
    label = ((element or {}).get("label") or "").strip()
    if risk == "password":
        what = "Type into a password or PIN field" if kind == "type" else "Tap a password or PIN field"
    elif kind == "type":
        what = f'Type into "{label}"' if label else "Type into the focused field"
        if typed:
            what += f': "{typed[:40]}"'
    elif label:
        what = f'Tap "{label}"'
    else:
        what = "Do this on your phone"
    consequence = _CONSEQUENCE.get(risk, "This needs your approval.")
    because = (why or "").strip()
    if because and because not in consequence:
        why_line = consequence + " " + because
    else:
        why_line = consequence
    return _TITLES.get(risk, "Approve"), what, why_line


def explain_request(rec):
    minutes = load_policy()["session_minutes"]
    if rec.get("armed"):
        names = ", ".join(
            f"{n} ({p})" if p else n
            for n, p in zip(rec.get("names") or [], rec.get("packages") or []))
        return (
            f"Cash-on-delivery auto-complete is armed for {names} for {minutes} minutes. "
            "Finish that order, including the final place-order button, only while the screen shows "
            "cash or pay on delivery, and the items on screen are the ones in the request. "
            "If a card, UPI, or wallet is selected, switch to cash on delivery. "
            "If cash on delivery is not offered, it is unchecked, or the cart has other items, "
            "placing the order shows the approval card. "
            "Call set_owner_request again for the next thing the owner asks."
        )
    if rec.get("cod") and not rec.get("packages"):
        return (
            "The request mentions cash on delivery but not an installed shopping app, "
            "so the order needs the approval card. Name the app, for example "
            "'order milk on Blinkit, cash on delivery'. Payment apps always need the card."
        )
    if rec.get("packages") and not rec.get("cod"):
        return "The request names an app but not cash on delivery, so the purchase needs the approval card."
    return "No cash-on-delivery order was requested. Purchases need the approval card."


def explain_checkout(app, elements, store=None):
    store = store or get_store()
    cfg = load_policy()
    req = store.request()
    state = payment_state(elements)
    sample = "Place order"
    gate = purchase_gate(cfg, req, app, sample, elements, {"kind": "button", "label": sample})
    would = {
        "auto": "place the order with no extra card, and log it",
        "switch": "refuse the tap until the payment method is cash on delivery",
        "card": "show the approval card",
        "navigate": "continue",
        None: "show the approval card if that button is a purchase",
    }[gate]
    lines = [
        f"app: {app or 'unknown'}",
        f"payment: {state}",
        f"total: {screen_total(elements) or 'not shown'}",
        f"cod_auto_complete: {'on' if cfg['cod_auto_complete'] else 'off'}",
        f"request_armed: {'yes' if req.get('armed') else 'no'}",
        f"place_order_would: {would}",
    ]
    if state == "cod_selected":
        problem = cart_problem(req, elements) if req.get("armed") else None
        if problem:
            lines.append("guidance: " + problem + " Do not place the order without the approval card.")
        else:
            lines.append("guidance: cash on delivery is the payment method, and the items on screen match the request. The final place-order button can complete the order.")
    elif state == "cod_unselected":
        lines.append("guidance: select Cash on delivery or Pay on delivery. Do not pay with a card, UPI, or wallet.")
    elif state == "cod_unavailable":
        lines.append("guidance: cash on delivery is not on this screen. Placing the order shows the approval card.")
    else:
        lines.append("guidance: no payment method is visible yet. Open checkout, then look again.")
    return "\n".join(lines)


def format_audit(rows):
    if not rows:
        return "No approvals or orders logged yet."
    lines = []
    for r in rows:
        if r.get("event") == "cod_order":
            lines.append(
                f"{r.get('ts')}  COD order  {r.get('app')}  {r.get('items')}  {r.get('total')}"
                + (f"  button {r.get('button')!r}" if r.get("button") else ""))
        else:
            bits = [r.get("ts", ""), r.get("event", ""), r.get("decision", ""), r.get("risk", ""),
                    r.get("action") or r.get("app") or ""]
            lines.append("  ".join(b for b in bits if b).rstrip())
    return "\n".join(lines)


def _plain_action(kind, element, typed):
    label = ((element or {}).get("label") or "").strip()
    if kind == "type":
        return f"type into {label or 'field'}" + (f" ({typed[:40]})" if typed else "")
    return f"tap {label}" if label else kind


def authorize(hub, *, kind, element=None, elements=None, why="", confirm=False, enter=False,
              agent="", typed="", seen_app=""):
    """Decide whether an action may run. Returns {approved, auto_cod}.

    approved is true only after the owner used the card (once or for the session).
    Password and PIN fields are refused before any card. auto_cod means the
    cash-on-delivery rule placed an order and wrote the audit log.
    """
    store = get_store()
    cfg = load_policy()
    if element and element.get("password"):
        raise ApprovalDenied(
            "password field: never type a password or PIN, even after an approval on the phone")
    ping = hub("ping") or {}
    if ping.get("stopped"):
        store.clear_session()
        raise ApprovalDenied("stopped by the owner (Stop button on the phone); ask the owner to tap Resume")
    app = ping.get("app") or ""
    elements = list(elements or [])
    label = ((element or {}).get("label") or "").strip()
    if element is not None and seen_app and app and seen_app != app:
        raise ApprovalDenied("the app in front changed since the last look(); call look() again")

    req = store.request()
    gate = purchase_gate(cfg, req, app, label, elements, element)
    risk = "payment" if gate == "card" else classify(kind, element, app, enter=enter)
    if gate == "card" and payment_state(elements) == "cod_selected":
        problem = cart_problem(req, elements)
        if problem:
            why = (problem + " " + why).strip() if why else problem

    if gate == "auto":
        fields = order_fields(store.request(), app, elements, label)
        store.audit("cod_order", agent=agent, **fields)
        return {"approved": False, "auto_cod": True}
    if gate == "navigate":
        return {"approved": False, "auto_cod": False}
    if gate == "switch":
        store.audit("cod_switch", agent=agent, app=_app_label(store.request(), app), package=app,
                    action=label, seeing=", ".join(prepaid_labels(elements)[:3]))
        raise ApprovalDenied(switch_message(elements))

    if risk is None:
        return {"approved": False, "auto_cod": False}
    if confirm and gate != "card":
        title, what, why_line = describe(risk, kind, element, why, typed)
        store.audit("approval", agent=agent, decision="chat_confirm", risk=risk, app=app,
                    action=what, why=why_line)
        return {"approved": False, "auto_cod": False}
    if store.allows(risk, app):
        store.audit("approval", agent=agent, decision="session", risk=risk, app=app,
                    action=_plain_action(kind, element, typed))
        return {"approved": True, "auto_cod": False}

    title, what, why_line = describe(risk, kind, element, why, typed)
    timeout = cfg["approval_timeout_sec"]
    result = hub("ask", {
        "title": title, "text": what, "why": why_line, "risk": risk, "timeout": timeout,
    }, timeout + 15)
    answer = str((result or {}).get("answer") or "timeout").lower()
    if answer == "allow":
        answer = "allow_once"
    store.audit("approval", agent=agent, decision=answer, risk=risk, app=app, action=what, why=why_line)
    if answer == "allow_session":
        store.grant(risk, app, cfg["session_minutes"], agent)
        return {"approved": True, "auto_cod": False}
    if answer == "allow_once":
        return {"approved": True, "auto_cod": False}
    raise ApprovalDenied(
        f"the owner did not allow it on the phone ({answer}). "
        "Ask them in chat, then repeat with confirm=true, or wait if they tapped Stop.")
