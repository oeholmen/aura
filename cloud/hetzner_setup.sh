#!/bin/bash
# cloud/hetzner_setup.sh
# RUN THIS ON THE HETZNER SERVER (as root)

set -e  # Exit on error

APP_DIR="/opt/aura"
USER="root" # change if you created a non-root cloud user

echo ">>> 1. SYSTEM UPDATE (ARM/AMD optimized)..."
apt update && apt upgrade -y
apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx ufw acl curl

echo ">>> 2. INSTALLING OLLAMA (The Neural Engine)..."
# Ollama's installer detects platform and installs the correct package
curl -fsSL https://ollama.com/install.sh | sh

echo ">>> 3. DOWNLOADING BRAIN MODELS (may take time)..."
echo "    ... Pulling Llama 3 (8B) for fast chat..."
ollama pull llama3 || true
echo "    ... (optional) Pulling nomic-embed-text for embedding services..."
ollama pull nomic-embed-text || true

echo ">>> 4. CONFIGURING FIREWALL (ufw)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw allow 8000/tcp # Aura Web UI
ufw --force enable

echo ">>> 5. PREPARING DIRECTORY..."
mkdir -p "$APP_DIR"
chown -R "$USER":"$USER" "$APP_DIR" || true

echo ">>> 6. CREATING SYSTEMD SERVICE (Auto-Restart)..."
cat <<'EOF' > /etc/systemd/system/aura.service
[Unit]
Description=Aura AGI Kernel
After=network.target

[Service]
User=__AURA_USER__
WorkingDirectory=/opt/aura
ExecStart=/opt/aura/venv/bin/python3 /opt/aura/ignition.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
# Add API Keys here or in a .env file
# Environment=OPENAI_API_KEY=your_key_here

[Install]
WantedBy=multi-user.target
EOF

# Replace placeholder user in service file if different from root
if [ "$USER" != "root" ]; then
  sed -i "s/__AURA_USER__/${USER}/g" /etc/systemd/system/aura.service
else
  sed -i "s/__AURA_USER__/root/g" /etc/systemd/system/aura.service
fi

systemctl daemon-reload
systemctl enable aura

echo ">>> 7. SETUP COMPLETE.\n    - Brain (Ollama) should be available at http://localhost:11434 if pull succeeded.\n    - Prepare to deploy your code into $APP_DIR and start the service with systemctl start aura" 

exit 0
