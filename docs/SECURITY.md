# Security

## Who can control your phone
Only something that has **all three**:
1. **Your Tailscale network:** the hub listens only on the machine's Tailscale address, never on
   the public internet. Only devices signed into your Tailscale account can reach it.
2. **Your hub key** (`hub.key`, created on your machine, readable only by your user). The phone
   must present it; wrong keys are rejected.
3. **Your phone's Mobile Use app**, switched on by you, connected to your hub.

Cloning this repo gives someone none of these. Every install has its own hub, key and app.

## What you control on the phone
- The **blue glow** and "AI agent is using your phone" notification always show while an agent acts.
- **Stop** blocks all agents for 30 minutes; **Resume** lifts it.
- **Allow / Deny** prompts for payment apps and Send/Pay/Buy/Delete buttons.
- Password and PIN fields are refused by the app itself, whatever the agent asks.
- Switch the app off any time in Settings → Accessibility.

## Keep these secret (never commit, never paste in chat)
`hub.key`, the app keystore (`*.keystore`) and its password, your Tailscale auth keys.
The repo's `.gitignore` covers them; check with `git status` before every push.

## Good habits
- Remove unknown devices from your Tailscale admin console.
- Use Tailscale ACLs if you share your tailnet: allow only your agent's machine to reach port 8765.
- Install the app only from your own build or the official Releases page.
- Review the agent's action log (`server/actions.log`) now and then.
