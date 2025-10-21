# Continuous Deployment Setup

## Overview

This project uses GitHub Actions to automatically:

1. **Build** Docker images for multiple architectures (amd64, arm64)
2. **Push** to GitHub Container Registry (GHCR)
3. **Deploy** to Raspberry Pi when pushing to `main`

## Workflow Triggers

- **Push to `main`**: Builds image and deploys to Raspberry Pi
- **Pull Requests**: Builds test images (no deployment)
- **Releases**: Builds versioned images (no automatic deployment)

## Setup Instructions

### 1. GitHub Secrets Configuration

Add the following secrets to your GitHub repository:
**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name   | Description                        | Example Value                            |
| ------------- | ---------------------------------- | ---------------------------------------- |
| `PI_HOST`     | Raspberry Pi IP address            | `10.250.1.103`                           |
| `PI_USERNAME` | SSH username on Pi                 | `gregoryleblanc`                         |
| `PI_SSH_KEY`  | Private SSH key for authentication | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

### 2. Generate SSH Key (if needed)

If you don't already have an SSH key for GitHub Actions:

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions@nhmesh-producer" -f ~/.ssh/github_actions_pi

# Copy the PUBLIC key to the Raspberry Pi
ssh-copy-id -i ~/.ssh/github_actions_pi.pub gregoryleblanc@10.250.1.103

# Test the connection
ssh -i ~/.ssh/github_actions_pi gregoryleblanc@10.250.1.103 "echo 'Connection successful!'"

# Copy the PRIVATE key content for GitHub secret
cat ~/.ssh/github_actions_pi
# Copy the entire output and paste into PI_SSH_KEY secret
```

### 3. Raspberry Pi Setup

Your Raspberry Pi is currently using **Portainer** to manage containers at:

- Container 1: `/data/compose/47/` (nhmesh-producer)
- Container 2: `/data/compose/50/` (nhmesh-producer-mf)

Ensure your Raspberry Pi has:

1. **Docker and Docker Compose installed**

   ```bash
   docker --version
   docker-compose --version
   ```

2. **Portainer Agent running** (already configured)

   ```bash
   docker ps | grep portainer_agent
   ```

3. **User has sudo access** (required for Portainer compose directories)

   ```bash
   sudo -l
   ```

4. **Containers are pulling from GHCR**
   - Check current image: `docker inspect nhmesh-producer --format='{{.Config.Image}}'`
   - Should be: `ghcr.io/nhmesh/producer:latest`
   - Update in Portainer if needed

### 4. Docker Compose Configuration

Ensure your `docker-compose.yml` uses the GHCR image:

```yaml
services:
  nhmesh-producer:
    image: ghcr.io/nhmesh/producer:latest
    container_name: nhmesh-producer
    restart: unless-stopped
    # ... rest of your config
```

## Deployment Process

When you push to `main`:

```bash
git add .
git commit -m "fix: resolve unhealthy container issues"
git push origin main
```

GitHub Actions will:

1. ✅ Build multi-arch Docker image (5-10 minutes)
2. ✅ Push to `ghcr.io/nhmesh/producer:latest`
3. ✅ SSH into Raspberry Pi
4. ✅ Find all docker-compose.yml files
5. ✅ Pull latest images
6. ✅ Recreate containers
7. ✅ Show deployment status

## Monitoring Deployments

### View GitHub Actions Run

1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select the latest workflow run
4. Check **Deploy to Raspberry Pi** job logs

### Check Pi Container Status

```bash
# Via Ansible
cd homelab-automation/ansible
ansible raspberry_pi -m shell -a "docker ps --filter 'name=nhmesh-producer'" -b

# Via SSH
ssh gregoryleblanc@10.250.1.103
docker ps
docker logs nhmesh-producer --tail 50
```

## Troubleshooting

### Deployment Fails with SSH Error

**Problem:** `Permission denied (publickey)`

**Solution:**

1. Verify `PI_SSH_KEY` secret contains the full private key
2. Test SSH connection manually:
   ```bash
   ssh -i ~/.ssh/your_key gregoryleblanc@10.250.1.103
   ```
3. Ensure public key is in `~/.ssh/authorized_keys` on Pi

### Docker Pull Fails on Pi

**Problem:** `Error response from daemon: pull access denied`

**Solution:**

1. Check if Pi is logged into GHCR:
   ```bash
   docker pull ghcr.io/nhmesh/producer:latest
   ```
2. Login to GHCR on Pi:
   ```bash
   echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
   ```
3. Or add imagePullSecrets to docker-compose

### Containers Not Found

**Problem:** Workflow can't find docker-compose.yml files

**Solution:**

1. Check where your compose files are:
   ```bash
   ssh gregoryleblanc@10.250.1.103 "find ~ -name 'docker-compose.yml' -path '*/nhmesh*'"
   ```
2. Update workflow script if needed to search correct directories

### Container Unhealthy After Deploy

**Problem:** Container shows as unhealthy after update

**Solution:**

1. Wait 40 seconds for healthcheck to stabilize
2. Check logs:
   ```bash
   docker logs nhmesh-producer
   ```
3. Verify fixes were included in the build
4. Check if container has `curl` installed:
   ```bash
   docker exec nhmesh-producer which curl
   ```

## Manual Deployment

If you need to deploy manually (bypassing GitHub Actions):

```bash
# On your local machine
ssh gregoryleblanc@10.250.1.103

# On Raspberry Pi
cd ~/nhmesh-producer
docker-compose pull
docker-compose up -d

# Verify
docker ps
docker logs nhmesh-producer --tail 20
```

## Rollback

If a deployment causes issues:

```bash
# On Raspberry Pi
cd ~/nhmesh-producer

# Use a specific version
docker-compose pull ghcr.io/nhmesh/producer:v1.2.3
docker-compose up -d

# Or use previous image (if still cached)
docker images | grep producer
docker tag ghcr.io/nhmesh/producer:<old-hash> ghcr.io/nhmesh/producer:latest
docker-compose up -d
```

## Security Notes

- 🔒 SSH private key is stored as GitHub secret (encrypted at rest)
- 🔒 Key is only used during workflow execution
- 🔒 No passwords stored in code
- 🔒 SSH key should be dedicated to GitHub Actions (not your personal key)
- 🔒 Consider IP whitelisting if your Pi has a firewall

## Additional Resources

- [GitHub Actions SSH Action](https://github.com/appleboy/ssh-action)
- [GHCR Documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Raspberry Pi Management Guide](../../homelab-automation/RASPBERRY_PI_MANAGEMENT.md)
