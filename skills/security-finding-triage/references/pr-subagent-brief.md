# Brief para el subagente que abre el PR

Lanza **un subagente por cada arreglo aprobado y por cada repo**: una misma causa raíz fijada en 3 repos son 3 PRs. Si hay varios, lánzalos en el mismo mensaje para que corran en paralelo. El subagente solo conoce lo que le pongas en el prompt, así que rellena la plantilla completa. El prompt va en inglés y el cuerpo del PR en español.

## Repos de la plataforma

| Repo (`~/Work/blend/adr/`) | Rama base | Tipo | Cómo se valida sin tocar AWS |
|---|---|---|---|
| `adr-medicalAudit-pipelineCDK` | `develop` | CDK TypeScript | `npx jest <suites afectadas>`; `./node_modules/.bin/tsc --noEmit` |
| `adr-iac-foundations` | `main` | CDK por subcarpeta (p. ej. `capacity-broker/`) | Dentro de la subcarpeta: `npm ci`, `npx jest` y `./node_modules/.bin/tsc --noEmit` |
| `IntelligentAuditEngine` | `main` | Terraform + Python | `terraform fmt -check -recursive infra/`; `terraform -chdir=<módulo> init -backend=false && validate`, borrando luego `.terraform/` y `.terraform.lock.hcl`; pytest |
| `AnomalyDetectionEngine` | `main` | Terraform + Python | Igual que IntelligentAuditEngine |

Confirma la rama base antes de lanzar el subagente. Usa `gh repo view --json defaultBranchRef` y mira la base de los últimos PRs mergeados con `gh pr list --state merged`.

## Aislamiento

`Agent(isolation: "worktree")` solo crea un worktree del repo principal de la sesión. Para cualquier otro repo, el subagente tiene que crear el suyo; **no confíes en que `isolation` lo haga por ti**. El checkout principal de un repo puede tener trabajo sin commitear de otra persona; ya pasó. El subagente nunca lo toca y, al terminar, confirma que el estado de ese checkout no cambió.

## Plantilla

```
Open a pull request against `<base>` in the repo at <repo-abs-path> (GitHub ai-scm/<repo>).

## Isolation (mandatory)
Never edit, stash, checkout or commit in the main checkout at <repo-abs-path>. Create your own worktree:
`git -C <repo-abs-path> fetch origin` then
`git -C <repo-abs-path> worktree add <repo-abs-path>-wt-<cve-or-control-lowercase> -b fix/<slug>-<cve-or-control-lowercase> origin/<base>`
and work with that worktree as cwd. Before finishing, run `git -C <repo-abs-path> status --short` and confirm the
main checkout shows exactly what it showed before you started.

## Goal
Remediate <source> findings in prod for <CVE-id | Security Hub control ID + title> on <resources this repo deploys>.
Root cause: <e.g. "public AppConfig Agent layer :262 built with go1.26.5" |
"FargateTaskDefinition construct in <file> omits readonlyRootFilesystem, so N task definitions fail ECS.5">.
Official remediation: <fixed version range | what the control evaluates, from its docs page>, <URL>.
Runtime risk to respect: <e.g. "the app writes to /tmp: mount a writable volume there" | "none">.

## The change (approved by the user; do exactly this, nothing more)
<file>:<line> — <before> -> <after>. <Why this version, and the alternatives rejected on purpose.>
Update comments/docs next to the change that state the old value. Run `git grep -n "<pattern>"` for other
hard-coded copies and update them consistently. Touch nothing unrelated; do not refactor.

## Steps
1. Edit. Validate with: <commands from the repo table>. Never run terraform plan/apply or cdk deploy/diff against AWS.
   - If pytest fails at import with `MissingDependencyException ... botocore[crt]`, that is the local
     ~/.aws login profile: rerun with `AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null
     AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_DEFAULT_REGION=us-east-1`, and report both runs.
   - Run tsc as `./node_modules/.bin/tsc`: through the rtk hook `npx tsc` has reported false errors.
   - Report real output. If something fails for a reason unrelated to this change, say so with the output and do not fix it.
2. One atomic commit, Conventional Commits, English, imperative, no trailing period, NO attribution lines.
   Stage explicit paths only (never `git add -A`). Never commit `docs/superpowers/` or `.terraform*`.
3. Push with `rtk proxy git push -u origin <branch>` (if a guard blocks rtk, `/usr/bin/git push -u origin <branch>`).
4. `gh pr create --base <base>`, Spanish body with: Resumen; Causa; Cambio; Alcance (ONLY the prod findings
   whose resources THIS repo deploys + their dev equivalents; link the sibling PRs in other repos); Pruebas;
   Verificación post-deploy; Fuentes (official URLs). Follow a `.github/` PR template if one exists.
   No attribution lines; no bare `@name`.
5. Do NOT merge, deploy or touch AWS.

## Report back
PR URL, branch, commit SHA, `git show --stat HEAD`, validation results quoted from actual output, and the
main-checkout status check.
```

## Después del subagente

- Comprueba tú mismo el resultado con `gh pr view <n> -R ai-scm/<repo> --json url,baseRefName,files` y `gh pr diff <n> -R ai-scm/<repo>`. Si el diff no coincide con lo aprobado, no lo reportes como listo.
- Si el subagente avisa de algo fuera de alcance (por ejemplo, un comentario en un repo que menciona el valor viejo de otro), anótalo para la revisión de los bots; no amplíes el PR por tu cuenta.
- Guarda el ID de cada subagente. En la revisión le mandarás con `SendMessage` los hallazgos VÁLIDOS para que los corrija en su mismo worktree.
