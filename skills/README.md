# Hermes project skills

This directory contains the Hermes-native migration of the project role definitions
previously stored in `.claude/agents/*.md`.

## Format and compatibility

Each skill uses Hermes' required directory layout:

```text
skills/<skill-name>/SKILL.md
```

The source role instructions are retained. Claude Code-only frontmatter (`tools`,
`model`, and `effort`) is omitted because Hermes chooses enabled tools and model
routing from its active profile. Every migrated skill records its source path in
frontmatter metadata.

## Enable in Hermes

Configure the project directory as an external skill directory:

```yaml
skills:
  external_dirs:
    - ~/Workspace/agent-crew/skills
```

Or set it through the CLI:

```bash
hermes config set skills.external_dirs '["~/Workspace/agent-crew/skills"]'
```

Start a new Hermes session after changing tool or skill configuration, then load a
skill explicitly with `/skill <name>` or allow Hermes to select it from the request.

## Migrated roles

- `architect` ← `.claude/agents/architect.md`
- `coo` ← `.claude/agents/coo.md`
- `critic` ← `.claude/agents/critic.md`
- `data-analyst` ← `.claude/agents/data-analyst.md`
- `devops` ← `.claude/agents/devops.md`
- `doc-reviewer` ← `.claude/agents/doc-reviewer.md`
- `engineer-go` ← `.claude/agents/engineer-go.md`
- `engineer-next` ← `.claude/agents/engineer-next.md`
- `engineer-vue` ← `.claude/agents/engineer-vue.md`
- `pm` ← `.claude/agents/pm.md`
- `pm-estimation` ← `.claude/agents/pm-estimation.md`
- `pm-learned-rules` ← `.claude/agents/pm-learned-rules.md`
- `pm-protocol` ← `.claude/agents/pm-protocol.md`
- `qa` ← `.claude/agents/qa.md`
- `retro` ← `.claude/agents/retro.md`
- `security` ← `.claude/agents/security.md`
- `ux-designer` ← `.claude/agents/ux-designer.md`
- `viral-video-researcher` ← `.claude/agents/viral-video-researcher.md`
