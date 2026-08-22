# GitLab CI Runners

The repository defines what CI runs. Each installation defines where it runs
through the required `CI_RUNNER_TAG` project CI/CD variable. The pipeline uses
the tag without providing a repository default:

```yaml
default:
  tags:
    - $CI_RUNNER_TAG
```

Set the variable in **Settings > CI/CD > Variables** for the GitLab project.
For example, a local installation might use `CI_RUNNER_TAG=ai-gov-local`.
Do not commit a private runner tag to this OSS repository. If the variable is
missing or does not match an online runner, CI jobs remain pending.

## Execution Options

### GitLab-hosted Runner

This is the simplest setup: configure `CI_RUNNER_TAG` with a tag available to
the GitLab-hosted runner for the installation. Jobs run on GitLab-managed
compute and consume the applicable GitLab compute quota.

### Self-Hosted Runner

With a self-hosted runner, GitLab.com remains the CI control plane while jobs
run on developer- or organization-managed infrastructure. This avoids
GitLab-hosted runner compute consumption, but the runner host must be online
and its runner process or service must be running whenever a job is queued.

The steps below use the `shell` executor, which is suitable for a trusted
development machine and makes the host's installed tools directly available to
CI.

1. Install GitLab Runner on the runner machine. On macOS with Homebrew:

   ```bash
   brew install gitlab-runner
   ```

2. In GitLab, create a project runner and copy the registration URL and token.
   Restrict its tags as appropriate for the project.

3. Register the runner locally with the `shell` executor. Provide the URL and
   token GitLab generated; do not add the token to a repository or shell
   history that is shared with others.

   ```bash
   gitlab-runner register --executor shell
   ```

   Give it a tag such as `ai-gov-local` when prompted.

   If a runner authentication token is exposed, treat it as compromised:
   rotate or reset it in **Settings > CI/CD > Runners** and follow GitLab's
   re-registration guidance before using the runner again.

4. Install Python 3.12 with `uv` on the runner host and ensure the account
   running GitLab Runner can find `uv` on its `PATH`:

   ```bash
   uv python install 3.12
   uv --version
   ```

5. In the project's GitLab CI/CD variables, set:

   ```text
   CI_RUNNER_TAG=ai-gov-local
   ```

6. Start the runner using the same ownership mode used during registration.
   A runner registered in user mode should remain in user mode; do not add a
   second system-level (`sudo`) registration. From the registering user's
   account, install and start the service:

   ```bash
   gitlab-runner install
   gitlab-runner start
   gitlab-runner status
   ```

   The status command should report that the service is running. Alternatively,
   run it in the foreground while validating the setup:

   ```bash
   gitlab-runner run
   ```

7. Confirm the runner shows as **Online** on the project's GitLab runners
   page and has the tag configured in `CI_RUNNER_TAG`, then run a pipeline
   from the GitLab UI.

## Shell Runners - Python Version

The `shell` executor runs commands against the runner host. Unlike a container
executor, it does not select a Python interpreter through a CI `image` value;
the active interpreter must be selected by the job itself. This pipeline does
so explicitly with `uv sync --frozen --python 3.12` and `uv run --python 3.12`.
It therefore does not inherit a developer's interactive virtual environment or
their default Python version.

Confirm Python 3.12 is available to the runner account before the first job:

```bash
uv python list
uv python install 3.12
```

## Security Boundary

A shell executor runs CI commands directly on the runner host with the runner
account's permissions. Attach a local runner only to repositories and
pipelines whose code you trust. Do not allow arbitrary fork or merge-request
pipelines to execute automatically on a developer shell runner.

This repository's pipeline intentionally does not create automatic pipelines
for ordinary feature-branch pushes or merge-request updates. It runs on `main`
and on pipelines explicitly started in the GitLab UI, which substantially
reduces accidental execution of unreviewed contribution code. It is still the
runner operator's responsibility to restrict project access, protected
variables, and manual pipeline permissions appropriately.
