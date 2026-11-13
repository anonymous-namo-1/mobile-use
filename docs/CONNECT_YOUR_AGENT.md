# Connect your AI agent

Two ways in. Use the MCP server if your agent supports MCP (best); otherwise use the `phone`
command, which any agent that can run shell commands can use.

Paths below assume the repo is at `~/mobile-use` and the venv at `~/mobile-use/server/.venv`.
The agent must run on the **same machine as the hub** (the MCP server talks to the hub through
`/tmp/phone-hub.sock`). Agent CLIs change; if a command below fails, check that agent's docs for
"add MCP server".

## Claude Code
```bash
claude mcp add phone -s user -- ~/mobile-use/server/.venv/bin/python ~/mobile-use/server/mcp_server.py
claude mcp list        # should show: phone ... Connected
```
Start a new Claude Code session. The first time, allow the phone tools ("don't ask again").

## Codex CLI
Add to `~/.codex/config.toml`:
```toml
[mcp_servers.phone]
command = "/home/YOU/mobile-use/server/.venv/bin/python"
args = ["/home/YOU/mobile-use/server/mcp_server.py"]
```

## Gemini CLI
Add to `~/.gemini/settings.json`:
```json
{ "mcpServers": { "phone": {
    "command": "/home/YOU/mobile-use/server/.venv/bin/python",
    "args": ["/home/YOU/mobile-use/server/mcp_server.py"] } } }
```

## Cursor
Add the same `mcpServers` block to `~/.cursor/mcp.json` (or the project's `.cursor/mcp.json`).

## Any other agent: the `phone` command
```bash
sudo install -m 755 server/phonectl /usr/local/bin/phone
phone help
phone look            # numbered list of buttons/fields on screen
phone click 7         # tap element 7
phone type 3 "hello" enter
phone open "WhatsApp"
```
For an agent on **another machine** (e.g. a chat bot), give it a restricted SSH user that may
only run `phone …` (see `server/restricted-ssh.md`), never a full shell.

## The tools (MCP)
| Tool | What it does |
|---|---|
| `look` | Screenshot with numbered boxes + list of buttons/fields/text. Start here. |
| `read_screen` | Just the list (fastest). |
| `tap(ref)` / `tap(x, y)` | Tap by number or position. |
| `type_text(text, ref, enter)` | Type any language/emoji into a field. |
| `scroll`, `swipe`, `press_key` | back, home, recent, notifications, quick_settings. |
| `open_app(name)`, `list_apps` | Open apps by name. |
| `wait_for(text)`, `find(text)` | Wait until something appears; scroll until it's visible. |
| `ask_owner(question)` | Approval card on the phone (slide to approve once or for this session, deny, or timeout). |
| `set_owner_request(text)` | The owner's verbatim request. Arms cash-on-delivery auto-complete when it names the app and COD. |
| `checkout_status()` | Which payment method checkout shows, and what a place-order tap will do. |
| `approval_log()`, `set_policy(on)`, `revoke_approvals()` | Audit log, the COD rule, session grants. |
| `status`, `wake` | Connection and lock state; turn the screen on. |

Safety built in: reading, scrolling, and opening apps just run. Paying, sending, deleting, and
installing show the approval card (slide; a tap does not approve). Password and PIN fields are
refused outright. `confirm=true` records that the person already agreed in chat; it does not
unlock a password field, and it does not skip the card when cash on delivery could not be
verified. Cash-on-delivery orders the person asked for, in an app they named, can complete
without the card only when checkout shows that payment method and the items on screen are the
ones they named. See the README.
