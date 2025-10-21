# Continuous Deployment Setup Summary

## ✅ What Was Added

### 1. Automatic Deployment on Push to Main

Modified `.github/workflows/docker-deploy.yml` to:

- **Trigger on push to `main` branch** (in addition to existing PR and release triggers)
- **Build multi-arch Docker images** (amd64, arm64)
- **Push to GitHub Container Registry** at `ghcr.io/nhmesh/producer:latest`
- **Automatically deploy to Raspberry Pi** via SSH

### 2. Deployment Job

Added `deploy-to-raspberry-pi` job that:

- Runs only on push to main (not PRs or releases)
- SSHes into Raspberry Pi at 10.250.1.103
- Finds all `nhmesh-producer*` containers
- Pulls latest images from GHCR
- Recreates containers using Portainer compose configs
- Verifies health status

### 3. Ansible Playbook for Manual Deployment

Created `homelab-automation/ansible/playbooks/raspberry-pi-update-nhmesh.yml` for:

- Manual deployments outside CI/CD
- Testing updates
- Troubleshooting

### 4. Documentation

Created comprehensive docs:

- `.github/DEPLOYMENT_SETUP.md` - Full setup guide
- Covers GitHub secrets, SSH keys, Portainer setup
- Troubleshooting section

## 🔑 Required GitHub Secrets

You need to add these to your GitHub repository settings:

| Secret        | Value                | Where to Add                 |
| ------------- | -------------------- | ---------------------------- |
| `PI_HOST`     | `10.250.1.103`       | Settings → Secrets → Actions |
| `PI_USERNAME` | `gregoryleblanc`     | Settings → Secrets → Actions |
| `PI_SSH_KEY`  | Your SSH private key | Settings → Secrets → Actions |

### Generating SSH Key

```bash
# Generate dedicated key for GitHub Actions
ssh-keygen -t ed25519 -C "github-actions@nhmesh-producer" -f ~/.ssh/github_actions_pi

# Copy public key to Pi
ssh-copy-id -i ~/.ssh/github_actions_pi.pub gregoryleblanc@10.250.1.103

# Test connection
ssh -i ~/.ssh/github_actions_pi gregoryleblanc@10.250.1.103 "echo 'Success!'"

# Copy private key to GitHub secret
cat ~/.ssh/github_actions_pi
# Paste entire output into PI_SSH_KEY secret
```

## 🚀 How It Works

### Automatic Deployment Flow

```
1. You push to main
   ↓
2. GitHub Actions builds Docker image (5-10 min)
   ↓
3. Image pushed to ghcr.io/nhmesh/producer:latest
   ↓
4. GitHub Actions SSHs to Raspberry Pi
   ↓
5. Pulls new image
   ↓
6. Stops old containers
   ↓
7. Recreates from Portainer compose
   ↓
8. Verifies health status
   ↓
9. ✅ Deployment complete!
```

### Manual Deployment via Ansible

```bash
cd homelab-automation/ansible
ansible-playbook playbooks/raspberry-pi-update-nhmesh.yml
```

## 📦 Portainer Integration

Your containers are managed by Portainer:

- **nhmesh-producer**: `/data/compose/47/`
- **nhmesh-producer-mf**: `/data/compose/50/`

The deployment script:

1. Extracts compose directory from container labels
2. Uses `docker-compose up -d --force-recreate` in that directory
3. Maintains Portainer compatibility

## 🧪 Testing the CD Pipeline

### Before Committing Secrets

1. Generate SSH key
2. Test SSH connection manually
3. Test pulling image manually:
   ```bash
   ssh gregoryleblanc@10.250.1.103 "sudo docker pull ghcr.io/nhmesh/producer:latest"
   ```

### After Setup

1. Make a small change (like updating a comment)
2. Commit and push to main:
   ```bash
   git add .
   git commit -m "test: verify CD pipeline"
   git push origin main
   ```
3. Watch GitHub Actions: `https://github.com/YOUR_ORG/nhmesh-producer/actions`
4. Check deployment logs
5. Verify containers on Pi:
   ```bash
   ssh gregoryleblanc@10.250.1.103 "docker ps --filter 'name=nhmesh-producer'"
   ```

## ✨ Benefits

- **No manual deployments** - Push to main, containers update automatically
- **Fast feedback** - See deployment results in ~10 minutes
- **Consistent** - Same process every time
- **Rollback support** - Easy to revert via git
- **Multi-container** - Updates both producer instances
- **Health checks** - Automatic verification post-deployment

## 🔧 Troubleshooting

See `.github/DEPLOYMENT_SETUP.md` for detailed troubleshooting including:

- SSH connection issues
- Docker pull failures
- Container recreation problems
- Health check failures

## 📚 Next Steps

1. **Add GitHub secrets** (PI_HOST, PI_USERNAME, PI_SSH_KEY)
2. **Test deployment** with a small commit
3. **Monitor first deployment** in GitHub Actions
4. **Verify containers** are healthy on Pi
5. **Commit bug fixes** to main and watch auto-deploy! 🎉

## 🔗 Related Files

- `.github/workflows/docker-deploy.yml` - Main CI/CD workflow
- `.github/DEPLOYMENT_SETUP.md` - Detailed setup guide
- `homelab-automation/ansible/playbooks/raspberry-pi-update-nhmesh.yml` - Manual deployment playbook
- `BUGFIX_UNHEALTHY_CONTAINERS.md` - Recent bug fixes to deploy

---

**Ready to deploy?** Add the GitHub secrets and push to main! 🚀
