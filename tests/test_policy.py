"""Pure tests for risk tiers and the cash-on-delivery purchase rule. No phone, no hub."""
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="mobileuse-policy-")
os.environ["PHONE_SESSION_FILE"] = os.path.join(TMP, "session.json")
os.environ["PHONE_OWNER_REQUEST"] = os.path.join(TMP, "request.json")
os.environ["PHONE_AUDIT_LOG"] = os.path.join(TMP, "audit.log")
os.environ["PHONE_POLICY_LOCAL"] = os.path.join(TMP, "policy.local.json")
os.environ.pop("PHONE_COD_AUTO_COMPLETE", None)

import sys
sys.path.insert(0, os.path.join(ROOT, "server"))
import policy


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        raise SystemExit(1)


def el(label, **extra):
    e = {"kind": extra.pop("kind", "button"), "label": label}
    e.update(extra)
    return e


def armed(app="Blinkit", package="com.blinkit.android"):
    return {"armed": True, "cod": True, "names": [app], "packages": [package],
            "text": f"order milk on {app}, cash on delivery", "ts": 10**12}


CFG = {"cod_auto_complete": True, "approval_timeout_sec": 60, "session_minutes": 30}


def main():
    check("reading is harmless", policy.classify("look") is None)
    check("opening an app is harmless", policy.classify("open", app="com.phonepe.app") is None)
    check("Send is a message", policy.classify("tap", el("Send")) == "message")
    check("Delete is delete", policy.classify("tap", el("Delete chat")) == "delete")
    check("Install is install", policy.classify("tap", el("Install")) == "install")
    check("Place order is payment", policy.classify("tap", el("Place order")) == "payment")
    check("password field is password", policy.classify("type", el("", password=True)) == "password")
    check("enter can send", policy.classify("type", el("Message"), enter=True) == "message")
    check("search enter does not send", policy.classify("type", el("Search"), enter=True) is None)
    check("tap inside a bank is payment", policy.classify("tap", el("Accounts"), app="com.phonepe.app") == "payment")

    apps = [{"name": "Blinkit", "package": "com.blinkit.android"},
            {"name": "PhonePe", "package": "com.phonepe.app"},
            {"name": "Cash", "package": "com.example.cash"}]
    matched = policy.match_apps("order milk on Blinkit, cash on delivery", apps)
    check("request names Blinkit", [a["package"] for a in matched] == ["com.blinkit.android"], str(matched))
    check("payment apps are not armable", policy.match_apps("pay on PhonePe, COD", apps) == [])
    check("the word cash is not an app", policy.match_apps("order milk, cash on delivery", apps) == [])

    cod = [el("Milk 1L", kind="text"), el("Cash on Delivery", kind="text", checked=True),
           el("To pay ₹199", kind="text"), el("Place order")]
    check("checked COD is selected", policy.payment_state(cod) == "cod_selected")
    check("only a COD line counts as selected",
          policy.payment_state([el("Payment method Cash on Delivery", kind="text")]) == "cod_selected")
    both = [el("UPI", checked=True), el("Cash on Delivery", checked=False), el("Place order")]
    check("UPI selected with COD offered is unselected", policy.payment_state(both) == "cod_unselected")
    check("UPI alone means COD is unavailable", policy.payment_state([el("UPI", checked=True)]) == "cod_unavailable")
    check("an available badge is not a selection",
          policy.payment_state([el("Cash on delivery available", kind="text")]) == "unknown")
    unchecked = [el("Milk 1L", kind="text"), el("Cash on Delivery", kind="text", checked=False), el("Place order")]
    check("an explicitly unchecked COD option is not selected",
          policy.payment_state(unchecked) == "unknown")
    check("Amazon Pay is prepaid", policy.payment_state([el("Amazon Pay balance", checked=True)]) == "cod_unavailable")

    req = armed()
    pkg = "com.blinkit.android"
    check("cart and checkout do not stop a COD order",
          policy.purchase_gate(CFG, req, pkg, "Checkout", cod) == "navigate")
    check("buy now on a product page continues",
          policy.purchase_gate(CFG, req, pkg, "Buy now", [el("Milk"), el("Cash on delivery available", kind="text")]) == "navigate")
    check("place order with COD selected is auto",
          policy.purchase_gate(CFG, req, pkg, "Place order", cod, el("Place order")) == "auto")
    check("an unchecked COD option does not auto-complete",
          policy.purchase_gate(CFG, req, pkg, "Place order", unchecked, el("Place order")) == "card")
    extra = cod + [el("Bread 400g", kind="text")]
    check("an extra cart item is not auto-completed",
          policy.purchase_gate(CFG, req, pkg, "Place order", extra, el("Place order")) == "card")
    check("place order on UPI asks to switch",
          policy.purchase_gate(CFG, req, pkg, "Place order", both, el("Place order")) == "switch")
    check("place order with no COD shows the card",
          policy.purchase_gate(CFG, req, pkg, "Place order", [el("UPI", checked=True)], el("Place order")) == "card")
    check("choosing the COD option is not the order",
          policy.purchase_gate(CFG, req, pkg, "Cash on Delivery", both, el("Cash on Delivery")) == "navigate")
    check("a different app is not covered",
          policy.purchase_gate(CFG, req, "com.amazon.mShop.android.shopping", "Place order", cod) is None)
    check("policy off never auto-completes",
          policy.purchase_gate({**CFG, "cod_auto_complete": False}, req, pkg, "Place order", cod) is None)
    check("PhonePe is never auto-completed",
          policy.purchase_gate(CFG, armed("PhonePe", "com.phonepe.app"), "com.phonepe.app", "Place order", cod) is None)

    items = policy.extract_items("please order a dozen eggs on Blinkit, cash on delivery")
    check("items come from the request", items == "dozen eggs", items)
    total = policy.screen_total(cod)
    check("total comes from the screen", total == "₹199", total)

    def hub(cmd, args=None, timeout=60):
        hub.calls.append((cmd, args or {}))
        if cmd == "ping":
            return {"app": pkg, "stopped": False}
        if cmd == "ask":
            return {"answer": hub.answer}
        raise AssertionError(cmd)
    hub.calls = []
    hub.answer = "deny"

    store = policy.get_store()
    store.save_request("order milk on Blinkit, cash on delivery",
                       [{"name": "Blinkit", "package": pkg}])
    decision = policy.authorize(hub, kind="tap", element=el("Place order"), elements=cod,
                                agent="test", seen_app=pkg)
    check("authorize places a verified COD order without asking",
          decision.get("auto_cod") and not any(c == "ask" for c, _ in hub.calls), str(hub.calls))
    rows = store.read_audit()
    order = rows[-1]
    check("the order log has app, items, total, and time",
          order["event"] == "cod_order" and order["app"] == "Blinkit" and order["items"] == "Milk 1L"
          and order["requested"] == "milk" and order["total"] == "₹199" and order["ts"], str(order))

    try:
        policy.authorize(hub, kind="tap", element=el("Place order"), elements=both, agent="test", seen_app=pkg)
        check("prepaid place-order is refused", False)
    except policy.ApprovalDenied as err:
        check("prepaid place-order tells the agent to switch", "not cash on delivery" in str(err), str(err))

    hub.calls.clear()
    try:
        policy.authorize(hub, kind="tap", element=el("Send"), elements=[el("Send")],
                         agent="test", seen_app=pkg)
        check("a denied card stops the action", False)
    except policy.ApprovalDenied as err:
        check("a denied card stops the action", "did not allow" in str(err) and hub.calls[-1][0] == "ask", str(err))
    check("the card says what and why",
          hub.calls[-1][1]["risk"] == "message" and "Send" in hub.calls[-1][1]["text"], str(hub.calls[-1][1]))

    hub.answer = "allow_session"
    hub.calls.clear()
    policy.authorize(hub, kind="tap", element=el("Send"), elements=[el("Send")], agent="test", seen_app=pkg)
    hub.calls.clear()
    again = policy.authorize(hub, kind="tap", element=el("Send"), elements=[el("Send")], agent="test", seen_app=pkg)
    check("session grant skips the second card",
          again.get("approved") and not any(c == "ask" for c, _ in hub.calls), str(hub.calls))

    hub.calls.clear()
    try:
        policy.authorize(hub, kind="type", element=el("PIN", password=True), confirm=True,
                         elements=[], agent="test", seen_app=pkg)
        check("a password field is refused", False)
    except policy.ApprovalDenied as err:
        check("a password field is refused with no card",
              "password" in str(err).lower() and not any(c == "ask" for c, _ in hub.calls), str(err))

    hub.answer = "deny"
    hub.calls.clear()
    try:
        policy.authorize(hub, kind="tap", element=el("Place order"), elements=extra,
                         agent="test", seen_app=pkg)
        check("an extra cart item needs the card", False)
    except policy.ApprovalDenied as err:
        asked = hub.calls[-1]
        check("an extra cart item needs the card and names the item",
              "did not allow" in str(err) and asked[0] == "ask" and "Bread 400g" in asked[1].get("why", ""),
              str(asked))

    stopped = lambda cmd, args=None, timeout=60: {"stopped": True, "app": pkg}
    try:
        policy.authorize(stopped, kind="tap", element=el("7"), agent="test")
        check("Stop clears the way", False)
    except policy.ApprovalDenied as err:
        check("Stop is reported and clears grants", "stopped" in str(err) and not store.allows("message", pkg), str(err))

    os.environ["PHONE_COD_AUTO_COMPLETE"] = "0"
    check("env turns the rule off", policy.load_policy()["cod_auto_complete"] is False)
    os.environ.pop("PHONE_COD_AUTO_COMPLETE")
    policy.set_cod_auto_complete(False)
    check("set_policy persists off", policy.load_policy()["cod_auto_complete"] is False)
    policy.set_cod_auto_complete(True)
    check("set_policy persists on", policy.load_policy()["cod_auto_complete"] is True)
    print("all policy checks passed")


if __name__ == "__main__":
    main()
