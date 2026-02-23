Deploying Aura to Hetzner (quick guide)

1) Pre-requisites
- Add your SSH public key to the Hetzner project security -> SSH keys.
- Confirm you can SSH to the server: `ssh bryan@89.167.60.243` (or the user you created).

2) One-shot automated deploy (from repo root)
```bash
# Example (replace with your user@host)
./scripts/deploy_hetzner.sh bryan@89.167.60.243 /opt/aura
```

3) After deploy
- Check service logs: `ssh bryan@HOST sudo journalctl -u aura.service -f`
- Verify health: `curl -sS http://127.0.0.1:8000/health` (run on server) or via nginx/domain if proxied.

4) Next hardening steps
- Replace `AURA_API_TOKEN` in `/etc/systemd/system/aura.env` with a strong secret and limit network exposure.
- Configure nginx and certbot for HTTPS.
- Disable root SSH password once keys are installed.
