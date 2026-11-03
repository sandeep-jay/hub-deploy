# hub-deploy

Deployment resources for JupyterHub.

Deploys JupyterHub for BIDS-managed hubs,
such as Berkeley's AI Futures Lab.

## Structure

This repo contains two charts:

1. `support` which contains per-cluster resources (Gateway, prometheus, grafana, cert-manager)
1. `hub` which deploys JupyterHub itself

For each _cluster_ `support` is deployed once.
For each _hub_, `hub` is deployed once.

Currently, we have one cluster (`demo`) and one hub (`demo`) on that cluster.

Cluster infrastructure (GKE, node pools, NFS disks, registry) is managed with OpenTofu under `tf/`.

## Deployment (nox, helm)

Deployment is done through `helm` via `nox`.

`helm` manages deployments on Kubernetes.

`nox` is our task runner to encapsulate the steps of things we do from this repo.

List available operations:

```
nox --list-sessions
```

To deploy the support chart for a cluster:

```
nox -s helm_support
```

To deploy the hub chart for a hub:

```
nox -s helm_hub
```

`CLUSTER_NAME` and `HUB_NAME` select the cluster and hub (both default to `demo`).

In order for these commands to work, files encrypted with `sops` must be decrypted (see below).
This generally means being logged in with the gcloud cli.

Deployments also run automatically from GitHub Actions on every push to `main` (see below).

## Secrets with SOPS

Secrets are managed using [sops](https://getsops.io).
Files containing sensitive information are named `$name.enc.$ext`, such as `hubs/demo/config.enc.yaml`,
and are encoded with `sops`.
The key is managed via Google Cloud KMS (see `.sops.yaml`), and authenticated with Application Default Credentials:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project bids-jupyterhub
```

You need `roles/cloudkms.cryptoKeyDecrypter` (or `cryptoKeyEncrypterDecrypter` to edit) on the `sops-key` key.

To edit a sops-encrypted file, run:

```bash
sops edit hubs/demo/config.enc.yaml
```

and you will get an editor with the decrypted contents of the file.
sops will then write back the updated encrypted file.

## Tasks

### Adding and updating packages

The user images are managed in this repo in subdirectories of `images/`.
The environment is (mostly) managed with [pixi],
so you can follow the pixi docs for various operations on the environment.
The image is built and published from GitHub Actions.

You can add packages to the image with:

```bash
cd images/$image_name
pixi add "$package=*"
```

And you can update specific packages with:

```bash
pixi update $package
```

You can update _all_ packages in the image with:

```bash
pixi update
```

Any package update change must include updates to `pixi.lock`.
So if you edit `pixi.toml` by hand instead of the pixi command-line, you'll need to run `pixi lock` to update the lockfile.

## Deploying from GitHub Actions

Deploys run from `.github/workflows/deploy.yaml` on push to `main`,
authenticated with GitHub Actions OIDC via Google Cloud Workload Identity Federation.
There are no credentials to manage: nothing is stored in GitHub secrets.

Sources:

- https://docs.github.com/en/actions/concepts/security/openid-connect
- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-google-cloud-platform
- https://github.com/google-github-actions/auth#preferred-direct-workload-identity-federation

We use direct Workload Identity Federation: IAM roles are bound directly to the GitHub identity,
with no intermediate service account.

Steps:

1. Create a Workload Identity Pool and an OIDC Provider for GitHub in it.
   The attribute condition restricts admission to this repository.
   (Requires `roles/iam.workloadIdentityPoolAdmin`, included in `roles/iam.admin`.)

   ```bash
   gcloud iam workload-identity-pools create github --location=global \
     --display-name="GitHub Actions" --project=bids-jupyterhub

   gcloud iam workload-identity-pools providers create-oidc github-actions \
     --location=global --workload-identity-pool=github --project=bids-jupyterhub \
     --display-name="GitHub Actions OIDC" \
     --issuer-uri="https://token.actions.githubusercontent.com" \
     --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.environment=assertion.environment,attribute.ref=assertion.ref" \
     --attribute-condition="assertion.repository == 'BIDS/hub-deploy'"
   ```

1. Grant the GitHub identity what it needs. We use a `deploy` environment on the repo to manage access,
   so the member is the set of identities in the pool whose `environment` attribute is `deploy`.
   (Requires project owner / `resourcemanager.projects.setIamPolicy`.)

   a. permission to decrypt with sops, scoped to the key in `.sops.yaml`:

   ```bash
   MEMBER="principalSet://iam.googleapis.com/projects/579170579029/locations/global/workloadIdentityPools/github/attribute.environment/deploy"

   gcloud kms keys add-iam-policy-binding sops-key \
     --keyring=sops --location=global --project=bids-jupyterhub \
     --role=roles/cloudkms.cryptoKeyDecrypter --member="$MEMBER"
   ```

   b. permission to deploy to GKE clusters in the project:

   ```bash
   gcloud projects add-iam-policy-binding bids-jupyterhub \
     --role=roles/container.admin --condition=None --member="$MEMBER"
   ```

1. (back on GitHub) create an Environment called `deploy` (must match `attribute.environment/deploy` in the bindings)
   with deployment branches restricted to `main`.

1. in a GitHub Actions workflow, add:

   ```yaml
   environment: deploy
   permissions:
     id-token: write
   ```

   and the steps:

   ```yaml
   - name: Configure Google Cloud credentials
     uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093 # v3.0.0
     with:
       project_id: bids-jupyterhub
       workload_identity_provider: projects/579170579029/locations/global/workloadIdentityPools/github/providers/github-actions

   - name: Install gke-gcloud-auth-plugin
     uses: google-github-actions/setup-gcloud@aa5489c8933f4cc7a4f7d45035b3b1440c9c10db # v3.0.1
     with:
       install_components: gke-gcloud-auth-plugin
   ```

Now we are at the point where any github action with access to the `deploy` environment can

1. authenticate with Google Cloud as the pool identity (Workload Identity Pool and Provider)
1. decrypt with `sops` (`roles/cloudkms.cryptoKeyDecrypter` on `sops-key`)
1. use the decrypted `kubeconfig`, which authenticates via `gke-gcloud-auth-plugin` using that identity
1. deploy to the cluster (currently all clusters in the project) with helm (`roles/container.admin`)

To check what the GitHub identity has been granted:

```bash
gcloud projects get-iam-policy bids-jupyterhub --flatten="bindings[].members" \
  --filter="bindings.members:principalSet*" --format="table(bindings.role,bindings.members)"
gcloud kms keys get-iam-policy sops-key --keyring=sops --location=global --project=bids-jupyterhub
```

The provider name, project number, and `principalSet` member are identifiers, not secrets.
A token from any other repository or environment is rejected.

[pixi]: https://pixi.prefix.dev
