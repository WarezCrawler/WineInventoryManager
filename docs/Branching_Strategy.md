# Branching Strategy

Date: 2026-11-15. Replaces the "one branch at a time, always from `main`" workflow. Reason: planned work (for example the module conversion in `Design_Evaluation.md`) must grow over many pull requests while `main` holds the latest released version only.

## 1. Branches

| Branch | Holds | Lifetime | Protected |
|---|---|---|---|
| `main` | The latest **released** version only. Every commit on `main` is a release or a hotfix. | Permanent | Yes |
| `develop` | The next release: all planned and finished work that is not released yet. | Permanent | Yes (same CI check) |
| `feature/<name>` | One change, from `develop` to `develop`. | Short (days) | No |
| `hotfix/<name>` | An urgent fix of the released version, from `main` to `main`. | Very short | No |

Releases are marked with a tag on `main`: `v1.0.0`, `v1.1.0`, and so on. The Windows program is built from a tag, never from `develop`.

## 2. Daily work

1. Update `develop`. Create `feature/<name>` from it.
2. Work, commit, open a pull request **to `develop`**.
3. The `test` check must pass. **Squash-merge.** Delete the branch (local and remote).
4. Repeat.

**Keep the old rule for feature branches:** one open feature branch at a time, no stacked branches, delete after merge. It still prevents the conflicts of the past (PR #2). The only change is the base: `develop` instead of `main`.

Large planned changes (for example the stock ledger) are cut into steps. Each step is its own feature branch and its own pull request, and each leaves `develop` green and releasable in principle. Do not keep a big branch open for weeks.

## 3. Release

1. `develop` is green and the release checks pass (see section 6).
2. Open a pull request **`develop` → `main`**. Title: `Release vX.Y.Z`.
3. Merge it with a **merge commit, not a squash.** A squash makes `main` and `develop` differ in history, and `develop` then looks "ahead" forever.
4. Tag the merge commit on `main`: `vX.Y.Z`. Build the program from the tag.
5. `develop` needs no reset. It already has all the content of `main`. GitHub shows `main` as one commit ahead after a release: that is the merge commit itself. It is harmless.

## 4. Hotfix

For an error in the released version, when `develop` holds work that is not ready.

1. Create `hotfix/<name>` from `main`. Fix it with a test.
2. Pull request to `main`, squash-merge, tag `vX.Y.Z+1`.
3. **Merge `main` back into `develop` at once** (pull request, merge commit). Do not forget this step. A fix that is only in `main` will be lost at the next release.

## 5. Database migrations and branches

Migrations are numbered, so two branches can use the same number.

- A migration that is **in `main`** is released. Never edit it (existing rule).
- A migration that is **only in `develop`** is not released. It may be edited or merged with another until the release. This is the exception that makes planned schema work cheap.
- A **hotfix should not change the schema.** If it must, it takes the next free number. When `main` is merged back into `develop`, the clashing `develop` migration is renumbered **before** any release, and never after.
- After a release the database of a user has been upgraded. From that point the migration is frozen.
- **Never open the live database with a `develop` build.** A `develop` build upgrades the file to a schema that is not released. The released program then refuses to open it, and only the backup copy brings it back. Always test on a copy.

## 6. Release checks

Before the release pull request:

- All tests pass on `develop`, including the golden tests.
- A rehearsal: copy a real database (a backup), start the new program on the copy, and check that the upgrade runs and the data is unchanged.
- The `Functionality.md` status and the README match what is built.
- The version and the release notes are written.

## 7. Settings to change (repository and CI)

1. **Create `develop` from `main` and protect it before the first release pull request.** Checked on 2026-11-15: one ruleset ("main: squash pull requests only") protects the default branch only. It blocks deletion and force push, requires a pull request and the `test` check, and allows squash merges only. `develop` is not covered. This matters: GitHub deletes the head branch of a merged pull request, and for a release pull request the head branch is `develop`. Add `develop` to the ruleset, or make a second ruleset for it with the same rules.
2. **Allow merge commits in two places.** The repository setting allows squash only, and the ruleset on `main` allows squash only. Both must also allow a merge commit. Without this, a release pull request can not be merged as in section 3. A squash release is not a substitute: after it, `main` does not have the commits of `develop`, and the next release pull request can give conflicts wherever the same lines changed both before and after the release. On `develop`, allow squash (features) and merge commit (the merge back after a hotfix).
3. **CI trigger:** `pull_request` already covers any target branch. Add `develop` to the `push` trigger, so the check also runs after a merge (done in `ci.yml`).
4. **Keep "delete branch on merge"** on. It is already on. It does not delete a branch that a ruleset protects against deletion, which is why item 1 comes first.
5. **Default branch:** keep `main`. A visitor of the public repository then sees the released version.

## 8. Alternatives (rejected for now)

| Alternative | Why not now |
|---|---|
| Only `main`, release by tag | Cannot keep unreleased planned work apart from the released version. |
| Release branches (`release/1.x`) with trunk development | Good for many versions in use at once. Here is one user and one live version. More work, no gain. |
| Long-lived feature branch for the module conversion | Grows stale and conflicts. Small steps into `develop` are safer. |
| Feature flags on `main` | Hides unfinished code in the released program. You want `main` to be released work only. |

Revisit release branches if two released versions must be supported at the same time.

## 9. Summary

`main` = released. `develop` = next release. Features go into `develop` by squash. Releases go into `main` by merge commit and a tag. Hotfixes go into `main`, then back into `develop`.
