# Setup — Cute Commit Garden for GitHub Profile

This repo generates a pastel "commit garden" grid (like GitHub's green squares, but cuter) that **includes commits from your private repos**.

## 1. Enable private contributions on GitHub

1. Go to [github.com/settings/profile](https://github.com/settings/profile)
2. Under **Contributions & activity**, check **Include private contributions on my profile**

Without this, private commits won't be counted in the API data.

## 2. Create your profile README repo

GitHub only shows a profile README from a repo named **exactly** your username.

1. Create a new repo: `jeanpeng1103/jeanpeng1103`
2. Set it to **Public**
3. Check **Add a README file** (or push this project)

## 3. Push this project to that repo

```bash
cd ~/Documents/projects/github-profile-graph
git init
git add .
git commit -m "add cute commit garden"
git branch -M main
git remote add origin https://github.com/jeanpeng1103/jeanpeng1103.git
git push -u origin main
```

## 4. Add a Personal Access Token secret

The workflow needs a token to read your private commit data.

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens) → **Fine-grained tokens** (or classic)
2. Create a token with:
   - **read:user**
   - **read:org** (if needed)
   - For fine-grained: access to your account, read-only on metadata
   - Classic alternative: just `read:user` scope works for GraphQL contribution calendar
3. In your `jeanpeng1103` repo → **Settings → Secrets and variables → Actions**
4. Add secret: `GH_PAT` = your token

## 5. Run it once manually

Repo → **Actions** → **Update commit garden** → **Run workflow**

The SVG updates daily at 8:00 UTC, or whenever you push / manually trigger.

## Customize colors

Edit `LEVELS` in `scripts/generate_graph.py` to tweak the pastel palette.
