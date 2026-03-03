# Development Rules

1. Always review relevant documents in the `docs/` directory before starting implementation.
2. If implementation changes require documentation updates, update the related files in `docs/` in the same work.
3. Split functions only as much as needed to enable meaningful unit testing. Avoid unnecessary fragmentation.
4. Always add and run unit tests for implemented behavior.
5. Use English only. Do not use Korean in code, documentation, tests, commit messages, or comments. Add only meaningful comments.
6. When content is updated, create a git commit that includes the change.
7. All tests must be executed within a controlled environment using `venv` and `Docker`. 
   - Use `venv` for local isolated Python environments.
   - Ensure tests can also run inside a `Docker` container for reproducibility and CI consistency.
   - Document setup and execution steps clearly in the project README.
8. Run the E2E script after implementation changes:
   - Local: `make e2e`
   - Docker: `make e2e-docker`
