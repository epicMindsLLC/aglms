# AGLMS PyCharm + GitHub CI/CD Setup Guide

## Overview

Your workflow after this setup:
1. Edit code in PyCharm on your Mac
2. `Cmd+K` → commit, `Cmd+Shift+K` → push to GitHub
3. GitHub Actions automatically SSHs into VPS, rebuilds Docker, deploys
4. ~60 seconds later: live at https://api.compcode.cloud

---

## Part 1: PyCharm Setup (Mac)

### Step 1 — Clone the repo in PyCharm

1. Open PyCharm
2. From the Welcome screen: **Get from VCS**
   - Or from menu: **File → New Project from Version Control**
3. Enter URL: `https://github.com/epicMindsLLC/aglms.git`
4. Choose a local directory (e.g. `~/Developer/aglms`)
5. Click **Clone**

### Step 2 — Set up Python interpreter

1. **PyCharm → Settings → Project: aglms → Python Interpreter**
2. Click the gear icon → **Add Interpreter → Add Local Interpreter**
3. Select **Virtualenv Environment** → **New**
4. Base interpreter: Python 3.12
5. Location: `~/Developer/aglms/.venv`
6. Click **OK**

### Step 3 — Install dependencies

Open the PyCharm Terminal (bottom panel) and run:

```bash
pip install -r backend/requirements.txt
```

### Step 4 — Add secret files (NOT committed to git)

Copy these two files from your VPS into `backend/` on your Mac:

```bash
# From your Mac terminal:
scp root@72.60.64.44:/opt/aglms/backend/lti_config.json ~/Developer/aglms/backend/
scp root@72.60.64.44:/opt/aglms/.env ~/Developer/aglms/
```

These are in `.gitignore` — they will never be committed to GitHub.

### Step 5 — Set up a Run Configuration for local testing

1. **Run → Edit Configurations → + → Python**
2. Name: `AGLMS Dev Server`
3. Script path: choose **Module name** → `uvicorn`
4. Parameters: `main:app --reload --port 8000`
5. Working directory: `~/Developer/aglms/backend`
6. Click **OK**

Press **▶ Run** to start the server locally at http://localhost:8000

---

## Part 2: VPS Setup — Git + SSH Deploy Key

Run these commands on the VPS to set up the repo and a deploy key.

### Step 1 — Generate a deploy SSH key on the VPS

```bash
ssh-keygen -t ed25519 -C "github-actions-vps-deploy" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Copy the output (starts with `ssh-ed25519 ...`).

### Step 2 — Add deploy key to GitHub

1. Go to: https://github.com/epicMindsLLC/aglms/settings/keys
2. Click **Add deploy key**
3. Title: `VPS Deploy Key`
4. Key: paste the public key output
5. ✅ Check **Allow write access** → **Add key**

### Step 3 — Configure SSH on VPS to use deploy key for GitHub

```bash
cat >> ~/.ssh/config << 'EOF'
Host github.com
    IdentityFile ~/.ssh/github_deploy
    StrictHostKeyChecking no
EOF
```

### Step 4 — Initialize the VPS repo

```bash
cd /opt/aglms

# Backup existing files
mkdir -p /tmp/aglms-backup
cp -r backend .env /tmp/aglms-backup/ 2>/dev/null; true

# Initialize git
git init
git branch -M main
git remote add origin git@github.com:epicMindsLLC/aglms.git
```

### Step 5 — Create the initial file structure on VPS

The repo needs these files committed (secrets stay out):

```
aglms/
├── .github/
│   └── workflows/
│       └── deploy.yml
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── docker-compose.yml
├── .gitignore
├── .env.example
└── README.md
```

Run on VPS:
```bash
cd /opt/aglms

# Create directory structure
mkdir -p .github/workflows

# .gitignore (keep secrets out of git)
cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
.venv/
venv/
.env
backend/lti_config.json
.idea/
.DS_Store
*.log
EOF

# .env.example (safe to commit — no real values)
cat > .env.example << 'EOF'
POSTGRES_USER=aglms
POSTGRES_PASSWORD=your_strong_password_here
POSTGRES_DB=aglms
DATABASE_URL=postgresql://aglms:your_strong_password_here@aglms-db:5432/aglms
SECRET_KEY=your_very_long_random_secret_key_here
DEBUG=false
CANVAS_URL=https://canvas.compcode.cloud
EOF
```

Then create `deploy.yml`:

```bash
cat > .github/workflows/deploy.yml << 'EOF'
name: Deploy to VPS

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Deploy to VPS via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            set -e
            cd /opt/aglms
            git pull origin main
            docker compose up -d --build aglms-api
            sleep 5
            curl -sf https://api.compcode.cloud/health && echo "✅ Deploy successful"
EOF
```

### Step 6 — Initial commit and push

```bash
cd /opt/aglms

git add .
git status   # verify no .env or lti_config.json are listed

git commit -m "Initial project structure with LTI 1.3 backend"
git push -u origin main
```

---

## Part 3: Verify the Full Pipeline

### Test 1 — GitHub Actions ran
Go to: https://github.com/epicMindsLLC/aglms/actions

You should see a green ✅ workflow run for your commit.

### Test 2 — API is live
```bash
curl https://api.compcode.cloud/health
# Expected: {"status":"ok","service":"AGLMS API","version":"0.1.0"}
```

### Test 3 — Make a change from PyCharm
1. Open `backend/main.py` in PyCharm
2. Change version from `"0.1.0"` to `"0.2.0"` in the health check
3. `Cmd+K` → commit with message "Bump version to 0.2.0"
4. `Cmd+Shift+K` → push
5. Watch https://github.com/epicMindsLLC/aglms/actions
6. After ~60s: `curl https://api.compcode.cloud/health` → should show `0.2.0`

---

## Part 4: Sprint Workflow

Once set up, every feature sprint looks like this:

```
Design feature
     ↓
Edit code in PyCharm (local server running at localhost:8000)
     ↓
Test locally with http://localhost:8000/docs (Swagger UI)
     ↓
Cmd+K → commit   |   Cmd+Shift+K → push
     ↓
GitHub Actions deploys to api.compcode.cloud (~60 sec)
     ↓
Test in Canvas at canvas.compcode.cloud
```

## Useful PyCharm Shortcuts

| Action | Shortcut |
|--------|----------|
| Commit | `Cmd+K` |
| Push | `Cmd+Shift+K` |
| Pull | `Cmd+T` |
| Git log | `Cmd+9` (then click Git tab) |
| Run server | `Ctrl+R` |
| Stop server | `Ctrl+F2` |
| Open terminal | `Alt+F12` |

---

## Troubleshooting

**GitHub Actions fails with "Permission denied"**
→ Check that `VPS_USER` secret is `root` and `VPS_SSH_KEY` is the correct private key.

**`git push` fails on VPS**
→ Run `ssh -T git@github.com` to verify the deploy key is working.

**`lti_config.json` missing after deploy**
→ This file is intentionally not in git. It lives at `/opt/aglms/backend/lti_config.json` on the VPS permanently and is never touched by deploys.

**Local server can't find `lti_config.json`**
→ Make sure you ran the `scp` command in Step 4 of Part 1.
