# Setup guide

For AI agents: do these steps **in order**, tell the person what each one is for in one line,
and check each result before moving on. `HOST` means the machine chosen in AGENTS.md step 1
(laptop, cloud server or home machine). Commands run on HOST unless it says "on the phone".

> **Status:** these steps work today. On a Linux server you can do steps 2 and 3a–3b with one
> command instead: [`install.sh`](../install.sh), documented in the [README](../README.md).
> One part is still manual either way: the person switches the app on in Accessibility (step 3c).
> A QR-code setup that removes ADB is planned, see [ROADMAP.md](ROADMAP.md).

## 1. Tailscale (private network between HOST and the phone)

Why: the phone and HOST find each other privately from anywhere, with no open ports.

1. On HOST: install Tailscale (https://tailscale.com/download), then `sudo tailscale up`
   (Mac: open the Tailscale app and sign in). The person approves the login link.
2. On the phone: install **Tailscale** from the Play Store, sign in with the **same account**,
   switch it on. Battery: Settings → Apps → Tailscale → Battery → **Unrestricted**.
3. Check on HOST: `tailscale status` lists the phone; `tailscale ip -4` prints HOST's address
   (100.x.y.z). Note it as `HUB_IP`.

## 2. The hub

Needs Python 3.10+ (`python3 --version`).

```bash
cd ~ && git clone https://github.com/anonymous-namo-1/mobile-use.git && cd mobile-use/server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # mcp, pillow
.venv/bin/python hub.py                         # first run creates hub.key; Ctrl+C after it starts
```

It should print `hub listening for the phone on 100.x.y.z:8765 (Tailscale only)`.
`hub.key` is the secret the phone will use. **Never share or commit it** (it's in `.gitignore`).

Keep it running:

- **Linux (laptop or server):** install the systemd unit from `server/phone-hub.service`
  (edit the user and paths), then
  `sudo systemctl enable --now phone-hub` and check `systemctl status phone-hub`.
- **Mac (laptop):** install the launchd agent from `server/phone-hub.plist`
  (edit the paths), then `launchctl load ~/Library/LaunchAgents/phone-hub.plist`.
  Remind the person: the Mac must stay awake while they want phone control.
- **Windows:** do this inside WSL2 (Ubuntu) with Tailscale installed in WSL; use the Linux steps.

If `tailscale ip` isn't found (Mac), start the hub with `PHONE_HUB_HOST=<HUB_IP>`.

## 3. The Mobile Use app

### 3a. Get the app (pick one)
- **Ready-made (easiest):** `dist/mobile-use.apk` in this repo. Check it first:
  `cd ~/mobile-use/dist && sha256sum -c mobile-use.apk.sha256` must print `OK`.
- **Build it yourself** (for people who prefer to): needs Java 17 and the Android command-line
  tools (the person accepts the Android SDK licence themselves). `cd app && ./build.sh` produces
  `build/mobile-use.apk`, signed with a key created on HOST. Never commit the keystore.

### 3b. Install and connect it (current method: ADB, once)
1. On the phone: Settings → About phone → tap **Build number** 7 times (Developer options),
   then Developer options → **Wireless debugging** → on. (Or plug in a USB cable with USB debugging.)
2. On HOST: install `adb` (`sudo apt install adb` / `brew install android-platform-tools`),
   pair with the code shown on the phone (`adb pair <phone-ip>:<pairing-port> <code>`), then
   `adb connect <phone-ip>:<port>`. The phone's Tailscale IP works as `<phone-ip>`.
3. Install and configure (run from `~/mobile-use`):
   ```bash
   adb install -r dist/mobile-use.apk
   adb shell pm grant dev.mobileuse.agent android.permission.POST_NOTIFICATIONS
   adb shell am broadcast -a dev.mobileuse.agent.CONFIG -n dev.mobileuse.agent/.ConfigReceiver \
       --es host <HUB_IP> --ei port 8765 --es key "$(cat server/hub.key)"
   ```
   (The config receiver only accepts this from ADB, so other apps on the phone can't change it.)
   It should answer `data="saved"`. Wireless debugging can be switched off afterwards.

### 3c. Switch it on (the person does this; never do it for them)
On the phone: Settings → **Accessibility** → Installed apps (or "Installed services") →
**Mobile Use** → **On** → **Allow**. If a "how to start or stop" shortcut pop-up appears, tap
Cancel and check the switch still says On.
- Greyed out / "Restricted setting" (Android 13+): Settings → Apps → Mobile Use → **⋮** →
  **Allow restricted settings**, then try again.
- Then: Settings → Apps → Mobile Use → Battery → **Unrestricted**.
A silent **"Mobile Use ready"** notification means it's connected. Brand-specific tips:
[PHONE_SETUP.md](PHONE_SETUP.md).

Check on HOST: `phone status` (after step 4) or the hub log says `phone connected: <model>`.

## 4. Connect your agent

See [CONNECT_YOUR_AGENT.md](CONNECT_YOUR_AGENT.md) (Claude Code, Codex, Gemini CLI, Cursor, or the
`phone` command for any other agent).

## 5. Test (harmless screens only)

1. `look`: the reply lists numbered buttons; the phone shows a **blue glow**.
2. Open the Calculator, tap 7 × 6 =, check it shows 42.
3. `ask_owner("Test: slide to approve")`: a card appears at the bottom of the phone. The person
   slides the thumb across (a tap does not count). Letting the timer run out denies it.
4. The person taps **Stop** in the "AI agent is using your phone" notification; the next action
   must fail with "stopped by the owner". Then they tap **Resume**.

Done. Tell the person how to use it and remind them about the glow and the Stop button.
