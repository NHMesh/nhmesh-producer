---
description: Build and push nhmesh-producer Docker image to GHCR (public) for field devices
---

# Deploy nhmesh-producer

The producer runs on field Raspberry Pis and is distributed via GHCR (public). CI automatically builds and pushes on merge to `main`.

## Deployment Flow

The primary deployment path is via GitHub Actions CI:

1. Commit and push changes to `main`:
```bash
cd /home/sk/personal/nhmesh-producer
git add -A && git commit -m "<message>"
```

2. Push to GitHub (triggers CI build):
```bash
git push upstream main
```

3. Push to Gitea (mirror):
```bash
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no" git push origin main
```

4. GitHub Actions will automatically:
   - Build multi-arch image (amd64 + arm64)
   - Push to `ghcr.io/nhmesh/producer:latest`
   - Tag with semver if releasing

## Field Producer Update

Field producers (Raspberry Pis) need to manually pull the new image:

```bash
# SSH into the producer Pi
docker pull ghcr.io/nhmesh/producer:latest
docker compose up -d --force-recreate
```

## Git Remote Configuration

- `origin` → Gitea: `ssh://git@git.glsec.us:2222/gitea_admin/nhmesh-producer.git`
- `upstream` → GitHub: `git@github.com:NHMesh/nhmesh-producer.git`

## Notes
- The producer image must be public on GHCR since field devices pull from it
- CI builds are triggered on push to `main` branch
- Field producers have backward compatibility for old/new field names
