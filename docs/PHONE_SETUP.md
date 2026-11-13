# Phone setup notes

## Requirements
- Android **11 or newer** (the app uses Android's accessibility screenshot API from Android 11).
- The **Tailscale** app, signed into the same account as the hub's machine.
- iPhone: not possible (iOS doesn't let apps control other apps).

## Permissions the app uses, and why
| Permission | Why | Who grants it |
|---|---|---|
| Accessibility service | Read the screen, tap, type, take screenshots | **The person**, in Settings → Accessibility |
| Notifications | Blue-glow notice with **Stop**, and a mirror of the approval card | Setup (ADB) or the person |
| Internet | Connect to the person's own hub over Tailscale | Automatic |
| Display over other apps (optional) | Lets the agent open apps from the background on some phones | Setup (ADB) or the person |

## Brand quirks
- **Samsung:** after switching it on, a "Choose how to start or stop this function" pop-up may
  appear: tap **Cancel** and check the switch is still On. Set Mobile Use's and Tailscale's
  Battery to **Unrestricted**; Samsung's battery saver ("freezing") otherwise drops the connection.
- **Xiaomi / Redmi / POCO:** also enable **Autostart** for Mobile Use and Tailscale, and set
  Battery saver to **No restrictions**.
- **OnePlus / Oppo / Realme / Vivo:** allow background activity and auto-launch; disable battery
  optimisation for both apps.
- **Android 13+ "Restricted setting":** apps installed outside the Play Store need
  Settings → Apps → Mobile Use → ⋮ → **Allow restricted settings** before Accessibility can be
  switched on.
- **Play Protect** may warn about an unknown app when installing the APK. That's expected for
  apps from GitHub; install only builds from the official Releases page or your own build.

## What the person sees
- **"Mobile Use ready"** (silent notification): connected, idle.
- **Blue glowing border + "AI agent is using your phone" with Stop:** an agent is in control.
  It disappears 15 s after the agent's last action.
- **Stop:** blocks every agent for 30 minutes (or until **Resume** is tapped).
- **Approval card** at the bottom (same blue as the glow): the agent wants to pay, send, delete,
  install, or type into a password field. Slide the thumb across to approve once or for this
  session. A tap does not approve. Deny, or let the timer run out, and nothing happens.
  Stop in the notification still works while the card is up.

## Banking apps
Many banking and payment apps block screenshots. The agent then sees the list of buttons but no
image. That's normal and by design.
