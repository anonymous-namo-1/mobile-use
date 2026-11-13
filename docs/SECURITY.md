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
- **Risky actions** (paying, sending, deleting, installing) show a card on the phone. Approving
  means sliding the thumb across, once or for this session. A tap does not approve. Deny, or
  doing nothing until the timer ends, refuses it.
- **Cash on delivery:** if you ask, in your own words, to order something in a named app and pay
  cash on delivery, the agent may place that order without the card. It only does so when the
  checkout screen shows cash / pay on delivery. A card, UPI, or wallet (including Amazon Pay)
  is not placed for you; the agent switches to cash on delivery, or the card appears if that
  option is not there, it is unchecked, or the cart contains something you did not ask for.
  Turn the rule off with `phone policy off` or `set_policy(false)`.
  Every such order is written to `server/audit.log` (app, the items on screen, total, time),
  along with approvals and denials.
- Password and PIN fields are never typed into. Approving a card, or `confirm=true`, does not change that.
- Switch the app off any time in Settings → Accessibility.

## Keep these secret (never commit, never paste in chat)
`hub.key`, the app keystore (`*.keystore`) and its password, your Tailscale auth keys.
The repo's `.gitignore` covers them; check with `git status` before every push.

## Good habits
- Remove unknown devices from your Tailscale admin console.
- Use Tailscale ACLs if you share your tailnet: allow only your agent's machine to reach port 8765.
- Install the app only from your own build or the official Releases page.
- Review the agent's action log (`server/actions.log`) now and then.
