# Roadmap: making setup easy for new users

Goal: a new user (or their AI agent) goes from zero to "agent uses my phone" in 10–15 minutes,
without Android tools or ADB.

- [x] **Prebuilt app** in `dist/` with a SHA-256 checksum (users can still build their own). Next: also attach it to GitHub Releases.
- [ ] **QR setup:** the hub prints a QR code (address + key); the app gets a setup screen that
      scans it. Removes ADB from setup entirely.
- [ ] **One-command installer** for the hub on Linux / Mac / WSL: creates the venv, the key, the
      service (systemd or launchd), and shows the QR code.
- [ ] **`mobile-use add <claude|codex|gemini|cursor>`** to register the MCP server automatically.
- [x] **Neutral package name** (`dev.mobileuse.agent`) and settings via environment variables.
- [ ] **Same-Wi-Fi mode** without Tailscale for people who only use it at home.
- [x] End-to-end smoke test with a fake phone + GitHub Actions (tests and Android build).
- [ ] Demo GIF in the README.
- [x] `phone` command uses the real screen size for scrolling.
