# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `phone not connected` | Mobile Use off, Tailscale off on the phone, or no internet | Phone: Tailscale on; Settings → Accessibility → Mobile Use on. Look for the "Mobile Use ready" notification |
| Connects, then drops every few seconds | Battery saver freezing the app (Samsung "Freecess", Xiaomi, etc.) | Battery → **Unrestricted** for Mobile Use and Tailscale (see PHONE_SETUP.md) |
| Hub log: `rejected …: wrong key` | Phone has an old key | Send the config again (SETUP.md 3b) or re-scan the QR (when available) |
| Hub won't start: "Tailscale is not up" | Tailscale off on HOST | `sudo tailscale up`; or set `PHONE_HUB_HOST=<tailscale ip>` |
| Accessibility switch greyed out / "Restricted setting" | Android 13+ sideload protection | Apps → Mobile Use → ⋮ → Allow restricted settings |
| Mobile Use turned itself off after an update | Some phones disable accessibility on app updates | Switch it on again in Accessibility |
| `stopped by the owner` | Someone tapped **Stop** | Tap **Resume** in the "AI agent stopped" notification |
| Approval card vanished and the agent says it was not allowed | The timer ran out (it denies on its own), or Deny was tapped | Ask again. Slide the thumb all the way across; a tap on the track does not approve. "This session" covers that kind of action in that app for 30 minutes |
| Agent will not place an order you asked for with cash on delivery | Checkout is not showing cash / pay on delivery, or the request did not name the app | It should switch a card, UPI, or wallet (including Amazon Pay) over to cash on delivery. If that option is not there, the approval card is the fallback. `phone policy` shows whether `cod_auto_complete` is on |
| `phone busy: … used it N s ago` | Another agent is driving the phone | Wait 2 minutes, or stop the other agent |
| Screenshot fails in an app | The app blocks screenshots (banking, DRM) | Use `read_screen`; the list still works |
| `PHONE LOCKED` | Screen lock is on | The person unlocks it. Agents never type the PIN |
| Laptop setup stops working | Laptop asleep or off (Option A) | Keep it awake while using phone control, or move to a server |
| Two "connected" lines per second in the hub log | Two copies of the app connecting | Update to the latest app (single-connection fix) |

Logs: hub `journalctl -u phone-hub -f` (Linux) or the terminal where it runs; phone
`adb logcat | grep -i mobileuse` (needs ADB).
