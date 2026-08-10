# Security Policy

## Supported Versions

AI Governance Control Plane is early-stage software. Security fixes are currently expected to target the main development line and the latest published release, when releases are available.

| Version | Supported |
| ------- | --------- |
| main | Yes |
| 0.1.x | Best effort |

## Reporting a Vulnerability

Please do not report confirmed or suspected vulnerabilities in public issues.

Use GitHub private vulnerability reporting if it is enabled for this repository. If it is not available, contact the maintainers through the most appropriate private channel available to the project and include only the information needed to establish secure communication.

Include the following when possible:

- Affected version or commit.
- Description of the vulnerability.
- Steps to reproduce or a minimal proof of concept.
- Impact and affected components.
- Any known mitigations.

Do not include live secrets, credentials, private datasets, customer data, proprietary prompts, or sensitive evaluation outputs.

## Scope

Security-sensitive areas include:

- Credential handling for model, evaluation, storage, and repository providers.
- Persistence layers and schema migrations.
- Evaluation data, prompts, datasets, model metadata, and experiment results.
- Workflow replay and audit records.
- APIs and adapters that expose governance decisions or leaderboard data.
- Logs, fixtures, and examples that may accidentally expose sensitive information.

## Response Expectations

Maintainers will make a best-effort attempt to acknowledge reports, assess severity, coordinate a fix, and communicate disclosure timing. Response times may vary while the project is early stage.

## Safe Research

Security research should avoid data destruction, service disruption, unauthorized access to third-party systems, or disclosure of private data. Test only against systems you control or have explicit permission to assess.
