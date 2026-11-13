# Instructions for AI agents setting up Mobile Use

You are helping a person set up **Mobile Use**: it lets AI agents (you, Claude Code, Codex,
Gemini CLI, Cursor, or any agent that can run shell commands) see and control **their own
Android phone**. Follow this file step by step. Talk to the person in plain, friendly language,
one step at a time, and wait for them when a step needs their hands on the phone.

> Claude Code reads `CLAUDE.md`, which points here. Codex and most other agents read `AGENTS.md`.

## If you were only given the link

That's expected: the person may have just pasted `https://github.com/anonymous-namo-1/mobile-use`
and said "set this up". Read this file (and the docs it links) from the repo, do **Step 0 and
Step 1 first**, and only then clone the repo **onto the machine they chose** (SETUP.md step 2).

- If you run on the person's own computer and they choose **Option A**, clone it here.
- If they choose **Option B/C** and you're on their computer, the server steps happen on the
  server: ask them to open an SSH session to it (they log in themselves; never ask for or type
  passwords) or to install you (Claude Code / Codex) on the server and continue there.

## Ground rules (always)

- This controls a real phone with real accounts. **Never** type passwords, PINs or one-time codes.
  **Never** make payments, purchases or send messages the person didn't ask for.
- Never change the phone's security settings yourself. Only the person switches on the
  Accessibility permission for the app.
- Never commit or print the hub's secret key (`hub.key`) or signing keys. Never put them in chat.
- If something fails twice, stop and explain what happened instead of trying random fixes.

## Step 0: check the basics

Ask, and confirm before going on:

1. **Phone:** Android 11 or newer? (Settings → About phone → Software information.)
   iPhone is not supported: Apple doesn't allow apps to control other apps. If they have an
   iPhone, say so kindly and stop.
2. **Agent:** which AI agent will use the phone (Claude Code, Codex, Gemini CLI, Cursor, other)?
3. **Computer:** Mac, Linux or Windows? (Windows works through WSL2, see `docs/HOSTING_OPTIONS.md`.)

## Step 1: let them choose where the hub runs

The **hub** is a small program the phone connects to. Your agent talks to the phone through it.
Present these options **exactly like this**, then ask them to pick:

> **Where should Mobile Use run?**
>
> **Option A: on this laptop/computer (free, quickest)**
> - Set up in about 10 minutes, nothing to pay.
> - **The catch:** the phone can only be controlled while this computer is **switched on, awake
>   and online**. Close the lid or let it sleep and the agent loses the phone until it wakes up.
> - Best if you'll use it while you're at your computer.
>
> **Option B: on a small cloud server (24/7)**
> - Works any time, even when your computer is off. Scheduled jobs can use the phone at night.
> - **The catch:** costs about US$4–6 a month for a small server (e.g. Hetzner, DigitalOcean,
>   Hostinger, Oracle's free tier), and setup takes about 20–30 minutes.
> - Best if you want it always available, or want your agents running on the server too.
>
> **Option C: a spare always-on machine at home** (Raspberry Pi, old PC, home server)
> - Free if you have one, 24/7 like a server, but you look after the hardware.

If they're unsure, recommend **A to try it out**; they can move to B later (it's the same
steps on another machine). Note their choice; the next steps say where they differ.

## Step 2: follow the setup guide

Go through [`docs/SETUP.md`](docs/SETUP.md) in order. It covers:

1. Tailscale on the computer/server and the phone (private connection, free).
2. Installing the hub and keeping it running (laptop or server variant).
3. Installing the Mobile Use app on the phone and connecting it to the hub.
4. Switching on the Accessibility permission (the person does this).
5. Connecting their agent: [`docs/CONNECT_YOUR_AGENT.md`](docs/CONNECT_YOUR_AGENT.md).
6. A short test.

Phone-specific help (Samsung, Xiaomi, battery savers, "restricted settings"):
[`docs/PHONE_SETUP.md`](docs/PHONE_SETUP.md). Problems: [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).
Security questions: [`docs/SECURITY.md`](docs/SECURITY.md).

## Step 3: finish

When the test passes, tell them in a few lines:
- how to use it ("ask me to do something on your phone"),
- the **blue glow** and the **Stop** button in the notification mean an agent is in control,
- for Option A: the computer has to stay on and awake while they want phone control.
