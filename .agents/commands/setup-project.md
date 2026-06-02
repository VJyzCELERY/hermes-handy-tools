---
description: Initializes or updates the .agents structure from a template repository
subtask: true
---

Initialize a new `.agents/` directory or update an existing one with improvements from MAIN-PROJECT-TEMPLATE.

**Query**: $1 (natural language query — specify the target directory, e.g., "set up .agents in ./my-new-project" or simply "./my-new-project")
> Load skill: setup-project (for bootstrapping .agents/)

**Template Source (Optional)**: $2 (GitHub repo URL, defaults to MAIN-PROJECT-TEMPLATE)

---

## Behavior

- **Fresh setup**: `.agents/` doesn't exist → clone entire template.
- **Soft update**: `.agents/` exists → compare each file against the template:
  - **New files** (in template, not in project) → copy in
  - **Updated files** (in both, but template is newer/different) → check if project has customizations:
    - If project file is mostly similar to template → replace with new template (template is authoritative for `.agents/` infrastructure)
    - If project file has significant project-specific additions → skip and flag it
  - **Removed files** (in project, not in template) → keep (project-specific)
  - **Custom subdirectories** (`reviews/`, `skills/`, project-specific docs) → always preserved

---

## Instructions

1. **Determine target**: `$1` (defaults to current directory)
2. **Determine source**: `$2` or `https://github.com/VJyzCELERY/MAIN-PROJECT-TEMPLATE`
3. **Clone template**:
   ```bash
   TMP_DIR=$(mktemp -d)
   git clone --depth 1 "$TEMPLATE_URL" "$TMP_DIR"
   ```

4. **Update `.agents/`**:

   ```bash
   AGENTS_DIR="$1/.agents"
   TEMPLATE_AGENTS="$TMP_DIR/.agents"
   mkdir -p "$AGENTS_DIR"

   echo "=== Soft update: $AGENTS_DIR ==="

   # Walk through every file in the template
   find "$TEMPLATE_AGENTS" -type f | while read -r tf; do
     rel="${tf#$TEMPLATE_AGENTS/}"
     target="$AGENTS_DIR/$rel"

     if [ ! -f "$target" ]; then
       # NEW file — copy from template
       mkdir -p "$(dirname "$target")"
       cp "$tf" "$target"
       echo "  + $rel (new)"
     else
       # EXISTING file — check similarity
       template_lines=$(wc -l < "$tf")
       diff_lines=$(diff --brief "$tf" "$target" 2>/dev/null && echo "0" || diff "$tf" "$target" | grep -c '^[<>]' 2>/dev/null || echo "999")
       total=$((template_lines > 0 ? template_lines : 1))
       similarity=$(( (total - (diff_lines / 2)) * 100 / total ))

       if [ "$diff_lines" -eq 0 ]; then
         # IDENTICAL — update to new template version
         cp "$tf" "$target"
         echo "  ~ $rel (updated)"
       elif [ "$similarity" -gt 80 ]; then
         # HIGHLY SIMILAR — project has minor tweaks, still safe to update
         cp "$tf" "$target"
         echo "  ~ $rel (updated — minor project tweaks overwritten, reapply if needed)"
       else
         # SIGNIFICANTLY DIFFERENT — project has customizations, skip
         echo "  · $rel (skipped — project has significant customizations)"
       fi
     fi
   done

   # Ensure .opencode symlink
   if [ ! -L "$1/.opencode" ]; then
     ln -sf .agents "$1/.opencode"
     echo "  + .opencode symlink created"
   fi

   echo "=== Update complete ==="
   ```

5. **Clean up**:
   ```bash
   rm -rf "$TMP_DIR"
   ```

---

## What Gets Updated vs Preserved

| File Type | Behavior |
|-----------|----------|
| Commands (`.agents/commands/*.md`) | Updated from template — template is authoritative |
| Templates (`.agents/templates/*.md`) | Updated from template |
| Agent rules (`.agents/docs/agents/*.md`) | Updated from template |
| Project rules (`.agents/docs/project_rules/*.md`) | Updated if similar (>80%), skipped if heavily customized |
| Scripts (`.agents/scripts/*.py`) | Updated from template |
| Skills (`.agents/skills/*/SKILL.md`) | Updated if from template, preserved if project-created |
| Reviews (`.agents/reviews/`) | Always preserved — project-specific |
| Custom files (anything project-added) | Always preserved |

## Required Context

- Preflight: none
- Skills: setup-project
- Rules: none
- Templates: none
- Mutates files: yes
- Mutates git history: no
- Mutates remote: no
- Requires user confirmation: yes (if target outside project root)

## Important

- Template is authoritative for `.agents/` infrastructure files (commands, templates, docs)
- Project-specific customizations in `.agents/` are preserved when they differ significantly
- To force a full refresh, delete `.agents/` and re-run setup
- The `.opencode` symlink is created if missing
