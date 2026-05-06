# Contributing to Recursant

Thanks for your interest in contributing! Recursant is an open-source
agentic mesh platform — issues, ideas, and pull requests are all welcome.

## Reporting issues

Before opening an issue, please:

1. Search [existing issues](https://github.com/ajensenwaud/recursant/issues)
   to avoid duplicates.
2. For bugs, include: what you expected, what happened, your environment
   (OS, Kubernetes flavour, Recursant commit/version), and steps to
   reproduce. Logs from `make k8s-logs` are usually enough.
3. For feature requests, describe the use case before the proposed
   solution — there may be an existing way to achieve what you need.

## Submitting a pull request

1. **Fork and branch.** Create a feature branch off `main`:
   `git checkout -b feature/short-description`.
2. **Keep PRs focused.** One concern per PR — separate refactors from
   bug fixes from new features. Reviewers will thank you.
3. **Tests.** Recursant uses real components in tests, not mocks. New
   features should land with integration tests that hit the running
   stack:
   ```bash
   make test                    # all tests
   make k8s-test                # k8s integration tests (requires running cluster)
   make k8s-test-registry       # registry only
   make k8s-test-banking        # mortgage demo only
   ```
4. **Code style.** Python: run `make lint`. Frontend: keep with the
   existing Tailwind / React patterns; we prefer functional components
   and hooks over class components.
5. **Commit messages.** Use conventional, imperative subject lines
   ("Add openrouter LLM provider", not "Added openrouter LLM provider").
   The body should explain *why* the change is needed, not just what
   changed.
6. **Open the PR** against `main` with a description of: what the change
   does, why it's needed, how it was tested, and any follow-up work
   that's intentionally out of scope.

## Local development

See [`INSTALL.md`](./INSTALL.md) for the full setup guide. Common
day-to-day commands:

```bash
./scripts/install.sh         # full bring-up from scratch
make k8s-status              # see what's running
make k8s-logs                # tail registry + webhook logs
make k8s-test-banking        # exercise the mortgage demo

# Rebuild + reload one image without a full cluster recycle:
docker build -t recursant-registry registry/
kind load docker-image recursant-registry --name recursant
kubectl rollout restart deployment/recursant-registry -n recursant
```

## Architecture and code layout

Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) before making large changes.
The project has two distinct planes:

- **Control plane** (`registry/`) — Flask app, Kafka consumers, React UI
- **Data plane** (`mesh/`) — sidecar process injected next to agents

Most features touch both planes. Look at recent commits for examples of
end-to-end changes (e.g. the OpenRouter provider integration is a good
template).

## Code of conduct

Be kind. Assume good faith. Critique ideas, not people. We don't have a
formal CoC document yet — until we do, the
[Contributor Covenant](https://www.contributor-covenant.org/) is the
default.

## License

By contributing, you agree that your contributions will be licensed under
the [MIT License](./LICENSE).
