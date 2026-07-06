# test-terraform-cloudbuild

Example repo that runs Terraform against GCP using **Cloud Build**, with:

- **Pull request** → `terraform plan` (`cloudbuild-plan.yaml`)
- **Merge to `master`** → `terraform apply` (`cloudbuild-apply.yaml`)
- **Private Terraform modules** fetched via a **GitHub App** token

Terraform creates a Cloud Storage bucket using the private [`storage-bucket`](https://github.com/ealebed/gcp-terraform-modules/tree/master/storage-bucket) module from `ealebed/gcp-terraform-modules`.

## Repository layout

```
.
├── cloudbuild-plan.yaml      # PR trigger → plan
├── cloudbuild-apply.yaml     # push to master → apply
├── scripts/
│   ├── github-app-token.py   # JWT → installation access token
│   └── post-pr-comment.py    # posts plan output back to the PR
└── terraform/
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    ├── terraform.tf
    ├── dev.tfvars            # per-environment variable values
    ├── stg.tfvars
    ├── prd.tfvars
    └── backend-config/       # per-environment remote state bucket
        ├── dev.hcl
        ├── stg.hcl
        └── prd.hcl
```

Variable values live in **`dev.tfvars` / `stg.tfvars` / `prd.tfvars`** (committed to the repo). Cloud Build only needs **`_ENVIRONMENT`** to select the right files.

## Prerequisites

| Item | Purpose |
|------|---------|
| GCP project | Hosts Cloud Build, Secret Manager, Terraform state, and the bucket |
| GCS state bucket | Remote Terraform state (create manually once) |
| GitHub App | Read access to private module repo `gcp-terraform-modules` |
| Cloud Build ↔ GitHub connection | Triggers builds from PRs and pushes |

---

## 1. Bootstrap GCP

Set your project and enable APIs:

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export STATE_BUCKET="${PROJECT_ID}-tf-state"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com
```

Create the Terraform state bucket (one-time):

```bash
gcloud storage buckets create "gs://${STATE_BUCKET}" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access
```

Grant the **Cloud Build service account** access to state and GCP resources:

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# State bucket
gcloud storage buckets add-iam-policy-binding "gs://${STATE_BUCKET}" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/storage.objectAdmin"

# Terraform needs these (adjust to least privilege for production)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/viewer"
```

---

## 2. GitHub App (private module access)

This mirrors the GitHub Actions flow that uses `tibdex/github-app-token@v2`.

### Create the app

1. GitHub → **Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**
2. Name it e.g. `gcp-terraform-modules-reader`
3. **Repository permissions**
   - **Contents**: Read-only (private Terraform modules)
   - **Pull requests**: Read and write (post plan output as a PR comment)
4. **Where can this app be installed?** → Only on this account/org
5. Create the app and note the **App ID**
6. Generate a **Private key** (downloads a `.pem` file)

### Install the app

1. **Install App** on your account/org
2. Grant access to **`gcp-terraform-modules`** (and this repo if it is private)
3. Note the **Installation ID** from the URL:  
   `https://github.com/settings/installations/<INSTALLATION_ID>`

### Store secrets in Secret Manager

```bash
# App ID and Installation ID as plain text
echo -n "123456" | gcloud secrets create GH_APP_ID --data-file=-
echo -n "98765432" | gcloud secrets create GH_APP_INSTALLATION_ID --data-file=-

# Private key PEM (entire file, including BEGIN/END lines)
gcloud secrets create GH_APP_PRIVATE_KEY --data-file=./your-app.private-key.pem
```

Grant Cloud Build access to read the secrets:

```bash
for SECRET in GH_APP_ID GH_APP_INSTALLATION_ID GH_APP_PRIVATE_KEY; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:${CLOUD_BUILD_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

> **Tip:** If the private key is stored with escaped newlines (`\n`), `scripts/github-app-token.py` normalizes them automatically.

---

## 3. Connect GitHub repo to Cloud Build

Cloud Build must be linked to GitHub before triggers can run on PRs/pushes.

### Option A — Google Cloud Console (recommended first time)

1. Open [Cloud Build → Repositories](https://console.cloud.google.com/cloud-build/repositories)
2. Click **Connect repository** (or **Create host connection** if using 2nd gen)
3. Select **GitHub (Cloud Build GitHub App)** or **Developer Connect**
4. Authenticate and select **`ealebed/test-terraform-cloudbuild`**
5. Finish the wizard

### Option B — gcloud (1st gen GitHub connection)

If you already connected GitHub at the project level:

```bash
# One-time: connect GitHub (opens browser)
gcloud builds triggers create github \
  --name="dummy-check" \
  --repo-name="test-terraform-cloudbuild" \
  --repo-owner="ealebed" \
  --branch-pattern="^master$" \
  --build-config="cloudbuild-plan.yaml" \
  --dry-run 2>/dev/null || true
```

If the connection is missing, use the Console wizard above — it installs the **Google Cloud Build** GitHub App on your repo.

### What gets connected

| Connection | Used for |
|------------|----------|
| **Google Cloud Build GitHub App** | Clones this repo when a trigger fires |
| **Your GitHub App** (`GH_APP_*` secrets) | Authenticates `terraform init` to pull private modules |

These are two different apps with different jobs.

---

## 4. Create Cloud Build triggers

Each trigger passes a single substitution: **`_ENVIRONMENT`** (`dev`, `stg`, or `prd`). The pipeline loads `terraform/${_ENVIRONMENT}.tfvars` and `terraform/backend-config/${_ENVIRONMENT}.hcl`, then selects the matching Terraform workspace.

| File | Purpose |
|------|---------|
| `dev.tfvars` | Variable values for dev |
| `stg.tfvars` | Variable values for stg |
| `prd.tfvars` | Variable values for prd |
| `backend-config/dev.hcl` | State bucket for dev (edit per env/project) |

### Plan on pull request (dev example)

```bash
export REPO="projects/ylebi-rnd/locations/us-central1/connections/ealebed-github/repositories/ealebed-test-terraform-cloudbuild"

gcloud builds triggers create github \
  --project=ylebi-rnd \
  --region=us-central1 \
  --name="terraform-plan-pr-dev" \
  --description="Terraform plan (dev) on PRs to master" \
  --repository="$REPO" \
  --pull-request-pattern="^master$" \
  --comment-control=COMMENTS_ENABLED \
  --build-config="cloudbuild-plan.yaml" \
  --substitutions="_ENVIRONMENT=dev"
```

Repeat for `stg` / `prd` with `--name="terraform-plan-pr-stg"` and `--substitutions="_ENVIRONMENT=stg"`, etc.

### Run plan on a pull request (`/gcbrun`)

With `--comment-control=COMMENTS_ENABLED`, Cloud Build does **not** run on every PR push by default. To start (or re-run) the plan:

1. Open a PR targeting `master`
2. Comment **`/gcbrun`** on the PR
3. Cloud Build runs `cloudbuild-plan.yaml`
4. On success, the plan output is posted as a **collapsible PR comment**

> Owners/collaborators can also trigger builds via `/gcbrun` after new commits. See [Cloud Build comment controls](https://cloud.google.com/build/docs/automating-builds/github/build-repos-from-github#comment_control).

### Plan output on the PR

After a successful plan, `scripts/post-pr-comment.py` posts `terraform show` output to the PR using the GitHub App token. Requires **Pull requests: Read and write** on the app (see section 2).

Manual `gcloud builds submit` skips the comment step (`_PR_NUMBER` is unset).

### Apply on merge to master (dev example)

```bash
gcloud builds triggers create github \
  --name="terraform-apply-dev" \
  --description="Terraform apply (dev) on push to master" \
  --repo-name="test-terraform-cloudbuild" \
  --repo-owner="ealebed" \
  --branch-pattern="^master$" \
  --build-config="cloudbuild-apply.yaml" \
  --substitutions="_ENVIRONMENT=dev"
```

### Trigger behaviour

| Event | How to trigger | Pipeline | Result |
|-------|----------------|----------|--------|
| PR → `master` | Comment `/gcbrun` | `cloudbuild-plan.yaml` | Plan + PR comment |
| Push → `master` | Automatic on merge | `cloudbuild-apply.yaml` | `apply -var-file=dev.tfvars` |

> **Tip:** To plan all environments on every PR create one trigger per environment — each differs only by `_ENVIRONMENT`.

---

## 5. How the pipeline works

Both `cloudbuild-*.yaml` files follow the same auth flow:

```
Secret Manager          Python script              Git + Terraform
──────────────          ─────────────              ───────────────
GH_APP_ID          →    Build JWT (RS256)    →   git config url.insteadOf
GH_APP_INSTALLATION_ID  Exchange for           →   terraform init (private modules)
GH_APP_PRIVATE_KEY      installation token
```

Equivalent GitHub Actions steps (for reference):

```yaml
- uses: tibdex/github-app-token@v2
- run: |
    echo $TOKEN | gh auth login --with-token
    gh auth setup-git
```

Cloud Build equivalent:

```bash
python scripts/github-app-token.py > /workspace/github_token.txt
git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
```

Cloud Build injects secrets via `availableSecrets.secretManager` — no plaintext keys in the YAML.

---

## 6. Local development

```bash
cd terraform
ENV=dev

# For private modules locally, use a PAT or gh auth:
export GITHUB_TOKEN="$(gh auth token)"
git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"

terraform init -backend-config="backend-config/${ENV}.hcl"
terraform workspace select "${ENV}" || terraform workspace new "${ENV}"
terraform plan -var-file="${ENV}.tfvars"
```

Edit `dev.tfvars` / `stg.tfvars` / `prd.tfvars` directly — same workflow as GitHub Actions.

---

## 7. Manual test (without waiting for a PR)

```bash
gcloud builds submit . \
  --config=cloudbuild-plan.yaml \
  --substitutions="_ENVIRONMENT=dev"
```

> `gcloud builds submit` uses the Cloud Build service account and Secret Manager bindings above. It does not test the GitHub PR trigger itself.

---

## 8. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `terraform init` 401/404 on module | GitHub App missing **Contents: read** on `gcp-terraform-modules`, or wrong `_MODULE_REF` |
| `Permission denied` on Secret Manager | Cloud Build SA lacks `secretAccessor` on `GH_APP_*` secrets |
| `Error loading backend` | Wrong bucket in `backend-config/<env>.hcl`, or Cloud Build SA lacks `storage.objectAdmin` on state bucket |
| `Missing dev.tfvars` | `_ENVIRONMENT` does not match a `*.tfvars` file in `terraform/` |
| `jwt` / `invalid key` | PEM malformed in Secret Manager; re-upload full `.pem` file |
| PR comment not posted | Do not set `_PR_NUMBER` in `cloudbuild-plan.yaml` substitutions (it overrides the trigger value). GitHub App needs **Pull requests: Read and write** |
| PR trigger does not fire | Comment `/gcbrun` on the PR, or check GitHub ↔ Cloud Build connection / branch pattern (`master`) |
| `terraform apply` changes on every plan | Pin module `ref` to a release tag instead of `master` |

---

## 9. Security notes

- Plan and apply use the same Cloud Build service account today. For production, use a dedicated Terraform SA with Workload Identity or keyless impersonation, and restrict apply permissions.
- Prefer module release tags (`storage-bucket/v1.0.0`) over branch refs.
- Consider [approval gates](https://cloud.google.com/build/docs/automating-builds/create-manual-approval) before apply in production.
