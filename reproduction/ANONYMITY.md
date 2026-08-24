# Anonymous review checklist

The working tree already uses scientific package names. The review mirror still must not leak identity.

Before creating an Anonymous GitHub link:

1. Replace the public dataset URL and any account name in `README.md` and `DATA_CARD.md` with "anonymous review artifact, not for distribution."
2. Run `make identity` and require a clean result on the mirrored tree.
3. Remove acknowledgments, emails, local paths, notebook metadata, image metadata, API keys, and identifying commit metadata.
4. Keep only the Anonymous GitHub URL in the review manuscript.

`make identity` scans `paper/`, `reproduction/archived/`, and generated tables. It does not rewrite the private working tree.
