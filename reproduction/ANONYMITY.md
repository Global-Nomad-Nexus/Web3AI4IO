# Anonymous review checklist

The working repository still uses contributor directory names. The anonymous review mirror must not.

Before creating the Anonymous GitHub link:

1. Rename `Claire/` and `Shilin/` to role-neutral paths, or omit them from the mirror in favor of `reproduction/`.
2. Replace the public dataset URL and any account name in `README.md` and `DATA_CARD.md` with "anonymous review artifact, not for distribution."
3. Run `make identity` and require a clean result on the mirrored tree.
4. Remove acknowledgments, emails, local paths, notebook metadata, image metadata, API keys, and identifying commit metadata.
5. Keep only the Anonymous GitHub URL in the review manuscript.
6. Prepare an identity-stripped supplementary ZIP as backup.

`make identity` already scans `paper/`, `reproduction/archived/`, and generated tables. It does not rewrite the private working tree.
