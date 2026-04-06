# Step-by-Step GitHub Upload

## Where This Should Live On GitHub

Put this in its own top-level public repository.

Recommended owner:

- your personal GitHub account

Recommended repo name:

- `aura-consciousness-proof-kernel`

Recommended visibility:

- `Public`

Do **not** put this inside the private/full Aura repo.
Keep it separate so people can inspect the proof kernel without getting the rest of the system.

## Fastest Recommended Method

Use the GitHub website plus Terminal.
This is the cleanest way to preserve the folder structure.

## What You Already Have

Your ready-to-upload bundle is here:

- `/Users/bryan/Downloads/aura-consciousness-proof-kernel`
- `/Users/bryan/Downloads/aura-consciousness-proof-kernel.zip`

Use the folder, not the zip, for the git upload steps below.

## Step 1: Sign In

1. Open [GitHub](https://github.com).
2. Sign into the account you want this repo to live under.

## Step 2: Create The Repo

1. Open [https://github.com/new](https://github.com/new)
2. Under `Owner`, choose your personal account.
3. Set `Repository name` to:
   `aura-consciousness-proof-kernel`
4. In `Description`, paste:
   `Minimal, reproducible subset of Aura's consciousness stack: competitive attention, temporal continuity, self-prediction, homeostatic regulation, and hidden-state opacity measurement.`
5. Select `Public`.
6. Do **not** check:
   - Add a README
   - Add .gitignore
   - Choose a license
7. Click `Create repository`.

## Step 3: Upload From Terminal

Open Terminal and run these commands exactly:

```bash
cd /Users/bryan/Downloads/aura-consciousness-proof-kernel
git init
git add .
git commit -m "Initial public proof kernel release"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/aura-consciousness-proof-kernel.git
git push -u origin main
```

Replace:

- `YOUR_GITHUB_USERNAME`

with your real GitHub username.

## Step 4: Edit The Repo Front Page

After the push finishes:

1. Refresh the repo page on GitHub.
2. Open the repo `About` settings on the right side.
3. Paste this description:
   `This repository is the public proof kernel behind Aura's consciousness-inspired architecture. It shows measurable internal state, temporal continuity, self-prediction, homeostatic regulation, and hidden-state opacity without publishing the full product stack.`
4. Add topics:
   - `artificial-consciousness`
   - `cognitive-architecture`
   - `attention`
   - `self-modeling`
   - `temporal-memory`
   - `homeostasis`
   - `computational-neuroscience`
   - `ai-research`
   - `agent-architecture`
   - `consciousness`

## Step 5: Pin The Right Files

Make sure these are visible in the repo root:

- `README.md`
- `UPLOAD_GUIDE.md`
- `STEP_BY_STEP_UPLOAD.md`
- `LAUNCH_COPY.md`
- `report.md`
- `report.json`

These are the files people will look at first.

## Step 6: First Public Description

In the repo description or your first post, say:

> This repository does not claim to prove subjective experience from the outside. It exposes the smallest public proof kernel behind Aura's consciousness-inspired architecture: measurable internal state, temporal continuity, self-prediction, homeostatic regulation, and hidden-state opacity.

## Step 7: Optional License Decision

Before adding a license, decide whether you mean:

- true open source
- or source-available only

If you want true open source, add an OSI-compliant license like MIT or Apache-2.0.
If you want inspectable but restricted use, use a source-available license and do not call it open source.

## If You Want To Upload Without Terminal

You can do it, but it is worse for a multi-file repo.

1. Create the new repo on GitHub.
2. Click `uploading an existing file`.
3. Open `/Users/bryan/Downloads/aura-consciousness-proof-kernel`.
4. Drag all files and folders from inside that folder into the GitHub upload page.
5. Scroll down to the commit box.
6. Use the message:
   `Initial public proof kernel release`
7. Click `Commit changes`.

This may work, but the Terminal method is much more reliable.

## Exact Best Place To Put It

Best choice:

- a brand new public repo under your personal GitHub account

Not recommended:

- inside the private Aura repo
- inside a monorepo
- inside a gist
- only as a zip attachment

## After It Is Live

Post the repo link together with the wording in `LAUNCH_COPY.md`.
