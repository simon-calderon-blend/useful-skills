# useful-skills

Personal Claude Code skills. Each skill lives in `skills/<name>/SKILL.md`.

- Create skills with `./scripts/new-skill.sh <kebab-name>`, never by hand-copying.
- Frontmatter `name` must equal the folder name; `description` must state what the skill does and when to use it.
- Keep `SKILL.md` concise; put long reference material in sibling files and link to them.
- Run `./scripts/validate.sh` before committing.
- Skills are installed by symlink (`./scripts/install.sh`), so edits here are live in `~/.claude/skills`.
