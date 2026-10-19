# Team Workflow

## Branch naming

- `feat/frontend-<scope>`
- `feat/agents-<scope>`
- `feat/tools-<scope>`
- `feat/qa-<scope>`
- `fix/<scope>`

## Commit conventions

- `feat: ...`
- `fix: ...`
- `test: ...`
- `docs: ...`

## Merge conflict avoidance

- Keep module ownership boundaries.
- Touch shared types in dedicated PRs.
- Rebase frequently and run local checks before requesting review.

## Example implementation flow

1. Open issue and pick owner.
2. Create branch using naming convention.
3. Implement in owned module first.
4. Add/update tests in `tests/`.
5. Run lint/typecheck/test/build.
6. Open PR using template.
