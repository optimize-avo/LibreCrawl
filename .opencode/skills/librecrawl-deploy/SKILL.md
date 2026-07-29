---
name: librecrawl-deploy
description: Deploy LibreCrawl to audit.avos.cx. Handles git commit, push to GitHub, Docker rebuild, and Cloudflare Tunnel verification. Load when user asks to commit, deploy, push, update, release, or publish changes to LibreCrawl.
---

# LibreCrawl Deployment Skill

This project uses **Docker** for the runtime and **Cloudflare Tunnel** (`cloudflared`) for public ingress. Deployment means:

1. Commit changes locally
2. Push to GitHub (`origin main`)
3. Rebuild & restart Docker container
4. Cloudflare Tunnel automatically routes `audit.avos.cx` → new container

## Infrastructure

```
audit.avos.cx
  ↓ (Cloudflare edge)
Cloudflare Tunnel (cloudflared)
  ↓ (tunnel to localhost:5001)
Docker container (librecrawl)
  ↓ 
Flask app (main.py)
```

- Cloudflare Tunnel config: `~/.cloudflared/config.yml` — maps `audit.avos.cx` → `http://localhost:5001`
- Docker compose: `docker-compose.yml` — builds from `Dockerfile`, mounts `./data:/app/data`, binds `127.0.0.1:5001:5001`
- GitHub: `origin` = `https://github.com/optimize-avo/LibreCrawl.git`

## Deployment Script

Run this to deploy:

```bash
# 1. Stage all relevant files (exclude generated/config files)
git add src/ web/ main.py

# 2. Commit
git commit -m "<descriptive message>"

# 3. Push to GitHub
git push origin main

# 4. Rebuild & restart Docker container
docker compose up -d --build
```

After step 4, verify with:
- `docker compose logs --tail=20` — check for startup errors
- `curl -sI http://localhost:5001` — local health check
- Browse `https://audit.avos.cx` — public endpoint

## Non-deployment rebuilds

If you only need to rebuild the Docker container (without pushing to GitHub):

```bash
docker compose up -d --build
```

## Common issues

| Problem | Solution |
|---------|----------|
| `docker compose` fails with permission | User is in `docker` group (verify with `groups`). If not, `sudo usermod -aG docker $USER` then re-login. |
| Cloudflare Tunnel down | Check `ps aux | grep cloudflared` or `journalctl -u cloudflared --no-pager -n 20` |
| Port 5001 already in use | `sudo lsof -i :5001` to find process, then `docker compose down && docker compose up -d` |
| `git push` rejected | Pull first: `git pull --rebase origin main`, resolve conflicts, then push again |
| Image too large | Check `.dockerignore` excludes `node_modules/`, `venv/`, `__pycache__/`, `*.db`, logs |
