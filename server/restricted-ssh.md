# Letting an agent on another machine use the phone (restricted SSH)

For chat bots or agents that don't run on the hub's machine. They get an SSH user that can
**only** run `phone …` commands: no shell, no file access, no port forwarding.

```bash
sudo useradd -m -s /bin/bash phonebot
sudo groupadd -f phonehub && sudo usermod -aG phonehub phonebot   # may use the hub socket
sudo install -m 755 phonectl /usr/local/bin/phone
sudo tee /usr/local/bin/phone-only >/dev/null <<'SH'
#!/usr/bin/env python3
import os, shlex, sys
args = shlex.split(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
if not args or args[0] != "phone":
    sys.exit("only `phone ...` commands are allowed; try: phone help")
os.environ["PHONE_AGENT_NAME"] = "phonebot"
os.execv("/usr/local/bin/phone", ["phone"] + args[1:])
SH
sudo chmod 755 /usr/local/bin/phone-only
```
Add the bot's public key to `/home/phonebot/.ssh/authorized_keys` with a forced command:
```
command="/usr/local/bin/phone-only",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... bot
```
The hub creates its socket for the `phonehub` group (add `SupplementaryGroups=phonehub` to the
hub's systemd unit). The bot then runs e.g. `ssh phonebot@<hub-ip> phone look`.
