# Where to run the hub: laptop, cloud server or home machine

The phone keeps a connection to the **hub**. Your AI agent talks to the hub. So the phone can be
controlled only while the hub's machine is **on and online**. Pick based on when you need it.

| | A. Your laptop/computer | B. Cloud server | C. Home machine (Pi, old PC) |
|---|---|---|---|
| Cost | Free | ~US$4–6/month (some free tiers) | Free if you have one |
| Available | Only while it's on, awake and online | 24/7 | 24/7 if left on |
| Setup time | ~10 min | ~20–30 min | ~20–30 min |
| Good for | Trying it, using it at your desk | Scheduled jobs, agents on the server, always-on | Same as B without the bill |
| Catch | Lid closed / sleep = no phone control | Monthly cost; you manage a server | You look after the hardware and power |

## Option A: laptop or desktop

- **Mac:** works. Keep it awake while you need phone control (System Settings → Battery/Energy:
  prevent sleep when plugged in; or run `caffeinate -dims` in a terminal while you work).
- **Linux:** works. Disable automatic suspend while you need it.
- **Windows:** use **WSL2** (Ubuntu) and install Tailscale **inside WSL**, then follow the Linux
  steps. Native Windows isn't supported yet (the hub uses a Unix socket). Not tested yet.
- The hub can start automatically at login (`docs/SETUP.md`, step 2).

## Option B: cloud server (VPS)

- Smallest plan is enough: 1 vCPU, 1 GB RAM, Ubuntu 22.04/24.04.
- Providers: Hetzner, DigitalOcean, Vultr, Hostinger, Linode, or Oracle Cloud's free tier.
- **Security:** the hub only listens on the server's **Tailscale** address, never on the public
  internet, and needs a secret key. You don't need to open any firewall port for it.
- Your AI agent should run **on the same server** (e.g. Claude Code or Codex installed there,
  used over SSH or the app's remote mode), because local agents talk to the hub through a
  file socket on that machine. (An agent on another machine can use the `phone` command over SSH.)

## Option C: Raspberry Pi / home server

- Raspberry Pi 4/5 or any old PC with Linux. Same steps as a cloud server.
- Keep it on wired power and internet. Tailscale makes it reachable from anywhere.

## Moving later

Moving from A to B (or C) is just doing the setup again on the new machine and scanning/sending
the new connection details to the phone. The phone app only talks to one hub at a time.
