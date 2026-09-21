# useful-skills

Personal collection of [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills).

## Layout

```
skills/<name>/SKILL.md   one folder per skill (plus any references/, scripts/ it needs)
templates/skill/         starting point for new skills
scripts/new-skill.sh     scaffold a skill
scripts/install.sh       symlink skills into ~/.claude/skills
scripts/validate.sh      check frontmatter of every skill
.claude-plugin/          plugin + marketplace manifest
```

## Install

Symlinks (edits in this repo are live immediately):

```bash
./scripts/install.sh              # link all skills into ~/.claude/skills
./scripts/install.sh --uninstall  # remove only the links that point here
```

Existing files or symlinks owned by something else are never overwritten. Set
`CLAUDE_SKILLS_DIR` to install somewhere other than `~/.claude/skills`.

Or as a plugin, on any machine:

```
/plugin marketplace add simon-calderon-blend/useful-skills
/plugin install useful-skills@useful-skills
```

## Add a skill

```bash
./scripts/new-skill.sh my-skill   # kebab-case
$EDITOR skills/my-skill/SKILL.md
./scripts/validate.sh
./scripts/install.sh
```

The `description` in the frontmatter is what Claude uses to decide when to load
the skill, so say both what it does and when to use it. Keep `SKILL.md` short
and move long reference material into sibling files it links to.
