#!/usr/bin/env bash
# Run once on a fresh Hetzner Ubuntu 22.04 VPS as root.
# After this script, SSH back in as deploy user.
set -euo pipefail

DEPLOY_USER="deploy"
SSH_PORT=22  # change to non-standard port if desired

echo "==> Creating deploy user..."
id "$DEPLOY_USER" &>/dev/null || useradd -m -s /bin/bash "$DEPLOY_USER"
usermod -aG sudo,docker "$DEPLOY_USER"

echo "==> Copying authorized_keys to deploy user..."
mkdir -p /home/$DEPLOY_USER/.ssh
cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/authorized_keys
chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
chmod 700 /home/$DEPLOY_USER/.ssh
chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys

echo "==> Hardening SSH..."
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
systemctl restart sshd

echo "==> Configuring UFW firewall..."
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow "$SSH_PORT/tcp"
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Installing fail2ban..."
apt-get install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban

echo "==> Installing Docker..."
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable docker
systemctl start docker

echo "==> Installing Docker Compose plugin..."
apt-get install -y docker-compose-plugin

echo "==> Enabling automatic security updates..."
apt-get install -y unattended-upgrades
dpkg-reconfigure --priority=low unattended-upgrades

echo "==> Done. Now:"
echo "    1. SSH back in as $DEPLOY_USER"
echo "    2. Clone the repo to /opt/dadaai"
echo "    3. Copy infra/.env.example to infra/.env and fill in secrets"
echo "    4. cd infra && docker compose up -d"
