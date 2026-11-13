<div align="center">

# 📱 Mobile Use

### Give your AI agent hands on your Android phone.

**Claude Code · Codex · Gemini CLI · Cursor · any agent that can run a command**

[![tests](https://github.com/anonymous-namo-1/mobile-use/actions/workflows/ci.yml/badge.svg)](https://github.com/anonymous-namo-1/mobile-use/actions/workflows/ci.yml)
![Android 11+](https://img.shields.io/badge/Android-11%2B-3DDC84?logo=android&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-server-6E56CF)
![License: MIT](https://img.shields.io/badge/license-MIT-blue)

</div>

---

> **Set it up in one message.** Paste this to your AI agent:
>
> ```
> Set up Mobile Use for me: https://github.com/anonymous-namo-1/mobile-use
> ```
>
> It reads [AGENTS.md](AGENTS.md), asks whether to run on your **laptop** (free, but it has to
> stay on) or a **cloud server** (24/7, a few dollars a month), and walks you through the rest.

---

## What it does

Your agent can **see** your phone screen as a numbered list of buttons and fields (plus a
screenshot), and **act**: tap, type, scroll, open apps, wait for things to appear. Think
"computer use", but for the phone in your pocket, from anywhere.

```
You: "Report my Amazon package as not delivered."
Agent: look → open_app("Amazon") → tap [12] "Your Orders" → tap [4] "Power bank" →
       tap [7] "Says delivered, but it's not here" → tap [9] "Raise a Query" ✓
```

## Why it's different

| | Screenshot-only agents | ADB-based tools | **Mobile Use** |
|---|---|---|---|
| How it sees | Guesses from pixels | Slow UI dumps (~2–3 s) | Android accessibility tree, **~0.3 s** |
| How it taps | Coordinates | Coordinates | **By element number**, exact |
| Typing | Often ASCII only | ASCII only | **Any language + emoji** (नमस्ते 👍) |
| Works on mobile data / after reboot | Depends | ❌ Wi-Fi debugging only | ✅ app connects out over Tailscale |
| You can see & stop it | ❌ | ❌ | ✅ **blue glow + Stop button** |
| Approves risky actions | ❌ | ❌ | ✅ **slide to approve on the phone** |

*Speeds measured on a recent Samsung phone over Tailscale, hub on a small cloud server.*

## How it works

```mermaid
flowchart LR
    A[AI agent<br/>Claude Code, Codex, ...] -- MCP or `phone` CLI --> H[Hub<br/>your laptop or server]
    P[📱 Mobile Use app<br/>accessibility service] -- Tailscale, secret key --> H
```

- The **app** on the phone reads the screen and performs gestures through Android's
  accessibility service, and keeps a private connection **out** to your hub.
- The **hub** runs on your laptop or a small server, listens only on your Tailscale address and
  only accepts a phone that knows its secret key.
- Your **agent** uses the MCP tools (`look`, `tap`, `type_text`, …) or the `phone` command.

## You stay in control

- 🔵 A **glowing blue border** and an "AI agent is using your phone" notification whenever an agent acts.
- ⏹️ **Stop** in that notification blocks every agent for 30 minutes (**Resume** to undo). It keeps working while an approval card is up.
- ✅ Reading the screen, scrolling, and opening apps just happen. Paying, sending, deleting, installing, or a password field shows a **card** on the phone: slide to approve once or for this session. A tap does not approve. Deny, or ignore it, and the timer refuses.
- 🧾 If you ask to order something **cash on delivery** and you name the app, that order can finish on its own, including the place-order button, once checkout really shows cash / pay on delivery. Anything else (card, UPI, a wallet such as Amazon Pay) still needs the card. See below.
- 🔒 Password and PIN fields do nothing until you slide to approve.
- 🧑‍🤝‍🧑 Two agents never fight over the phone: a shared lock lets one drive at a time.

## Tools

| MCP tool | `phone` command | What it does |
|---|---|---|
| `look` | `phone look` | Numbered list of buttons/fields/text (+ screenshot with boxes) |
| `tap(ref)` | `phone click N` | Tap an element by number (or `tap(x, y)`) |
| `type_text(text, ref, enter)` | `phone type N "text" enter` | Type into a field, any language |
| `scroll`, `swipe`, `press_key` | `phone scroll down`, `phone key back` | Navigate |
| `open_app(name)` | `phone open "WhatsApp"` | Open apps by name |
| `find(text)`, `wait_for(text)` | `phone find "…"`, `phone wait "…"` | Scroll until visible / wait until it appears |
| `ask_owner(question)` | `phone ask "…"` | Approval card: slide once, slide for this session, deny, or timeout |
| `set_owner_request(text)` | `phone task "…"` | Record what you asked. Arms cash-on-delivery auto-complete when you named the app and COD |
| `checkout_status()` | `phone checkout` | Which payment method is selected, and what Place order will do |
| `approval_log()` | `phone log` | Approvals and cash-on-delivery orders (app, items, total, time) |
| `set_policy(on)` | `phone policy on\|off` | Turn cash-on-delivery auto-complete on or off (on by default) |

## One-command install (Linux)

On the machine that will run the hub:

```bash
curl -fsSL https://raw.githubusercontent.com/anonymous-namo-1/mobile-use/main/install.sh | bash
```

That clones or updates the repo, installs Python dependencies, creates the hub key, installs a
systemd service when Tailscale is already up, and installs the app with `adb` when **one** phone
is connected. It is safe to run again. It never runs `adb kill-server` or `adb disconnect`, and
it never passes `-s` (the adb server may be shared).

To install a branch other than `main`:

```bash
curl -fsSL https://github.com/anonymous-namo-1/mobile-use/raw/refs/heads/<branch>/install.sh | MOBILE_USE_BRANCH=<branch> bash
```

You still sign Tailscale in yourself, and you still switch **Mobile Use** on under
Settings → Accessibility. macOS follows [docs/SETUP.md](docs/SETUP.md).

## Approvals

Harmless actions (look, scroll, open an app, type into an ordinary field) do not ask.
A risky one puts a card at the bottom of the phone, in the same blue as the glow:

- It says, in plain words, what the agent is about to do and why.
- **Slide** the thumb from the left to approve. A tap on the track does nothing.
- **Once** covers that single action. **This session** covers the same kind of action in the same app for 30 minutes (`phone revoke` clears it).
- **Deny**, or do nothing, and the timer refuses it. Stop in the notification still works.

The decision is appended to `server/audit.log`.

## Cash on delivery

`cod_auto_complete` is **on by default** (`server/policy.json`). Turn it off with
`phone policy off`, `set_policy(false)`, or `PHONE_COD_AUTO_COMPLETE=0`. A local override
lives in `server/policy.local.json`.

The rule applies only when the owner's own request **names the app** and **cash on delivery**
(also "pay on delivery" or "COD"). The agent records that request with `set_owner_request` /
`phone task`. It then:

1. Finishes the order, including the final place-order button, with no extra card.
2. Checks the checkout screen first. The selected method must be cash or pay on delivery.
3. If a card, UPI, or wallet (including Amazon Pay) is selected, switches to cash on delivery instead of paying.
4. If cash on delivery is not offered, falls back to the approval card.

Payment and banking apps always use the card. Every auto-completed order is logged with the
app, items, total, and time (`phone log`). Any other purchase uses the card.

## You need

- An **Android 11+** phone (iPhone can't do this: iOS doesn't allow it)
- A **laptop** or a small **cloud server** for the hub ([which one?](docs/HOSTING_OPTIONS.md))
- A free **Tailscale** account
- An **AI agent**

## Docs

| | |
|---|---|
| 🤖 [AGENTS.md](AGENTS.md) | The step-by-step script your AI agent follows |
| 🖥️ [Hosting options](docs/HOSTING_OPTIONS.md) | Laptop vs cloud server vs Raspberry Pi |
| 🛠️ [Setup](docs/SETUP.md) | All steps, if you'd rather do it yourself |
| 📱 [Phone notes](docs/PHONE_SETUP.md) | Samsung/Xiaomi battery savers, "restricted settings" |
| 🔌 [Connect your agent](docs/CONNECT_YOUR_AGENT.md) | Claude Code, Codex, Gemini CLI, Cursor, CLI |
| 🔐 [Security](docs/SECURITY.md) | Who can reach your phone (only you) |
| 🩺 [Troubleshooting](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| 🗺️ [Roadmap](docs/ROADMAP.md) | QR-code setup, same-Wi-Fi mode, … |

## FAQ

**Do I need a server?** No. Your laptop works; the catch is it has to be on and awake for your
agent to reach the phone. A small cloud server (or Raspberry Pi) makes it 24/7.

**Can people who clone this reach my phone?** No. Every install has its own hub, secret key and
app connection, inside your own Tailscale network. See [SECURITY.md](docs/SECURITY.md).

**Why not the Play Store?** Google is (rightly) strict with accessibility apps. Install the APK
from [`dist/`](dist/) (check its SHA-256) or build it yourself from [`app/`](app/).

## Project layout

```
install.sh  one-command Linux setup (clone, hub, MCP server, APK if a phone is connected)
app/        Android app (Java, no Gradle: javac + d8 + aapt2), build.sh
server/     hub.py · mcp_server.py · policy.py · phonectl (the `phone` command) · service files
dist/       ready-made APK + checksum
docs/       setup guides for humans and AI agents
tests/      policy tests and an end-to-end test with a fake phone (runs in CI)
```

## License

[MIT](LICENSE). Built with Claude Code.
