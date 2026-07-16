# Common Branch Plan

Breakdown planning is read-only. It records `version`, `approved`, lifecycle and
issue IDs, source/base refs and SHAs, final tree, diff summary, and ordered
slices. Every slice records its ID, branch, title, purpose, paths, intended
base, rationale, dependencies, changed-line counts, validation disposition,
review disposition and skip reason, exact commit list and boundary, and tree.

Only an artifact with `approved: true` may be applied. Any edit requires renewed
approval. Applying creates a backup branch before rewriting, rebuilds from the
recorded commits, and verifies the final tree. Approval permits local rewrite
and state writes only; push, force-push, and PR operations remain prohibited.
