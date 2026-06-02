"""Skills management commands."""

import click
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

from ..skills import get_skill_names, get_skill_content

console = Console()


@click.group()
def skills():
    """Manage OpenCode Python CLI skills."""
    pass


@skills.command("list")
def list_skills():
    """List all available skills."""
    names = get_skill_names()
    if not names:
        console.print("[yellow]no skills found[/yellow]")
        return
    
    console.print("Available skills:")
    for name in names:
        console.print(f"  [green]{name}[/green]")


@skills.command("get")
@click.argument("name", required=False)
def get_skill(name: str):
    """Get skill content. If no name, show all skills."""
    if name:
        content = get_skill_content(name)
        if content is None:
            console.print(f"[red]skill not found: {name}[/red]")
            raise SystemExit(1)
        console.print(Markdown(content))
    else:
        names = get_skill_names()
        for skill_name in names:
            content = get_skill_content(skill_name)
            if content:
                console.print(f"\n{'='*60}")
                console.print(f"[green]{skill_name}[/green]")
                console.print(f"{'='*60}\n")
                console.print(Markdown(content))


@skills.command("export")
@click.argument("file_path", required=False)
@click.option("--name", "-n", multiple=True, help="Export specific skill(s) by name")
def export_skills(file_path: str, name: tuple):
    """Export skills to a file. If no file path, export all skills."""
    output_path = Path(file_path) if file_path else None
    
    if name:
        # Export specific skills
        skill_names = list(name)
    else:
        # Export all skills
        skill_names = get_skill_names()
    
    if not skill_names:
        console.print("[yellow]no skills to export[/yellow]")
        return
    
    # Build export content
    content = []
    for skill_name in skill_names:
        skill_content = get_skill_content(skill_name)
        if skill_content:
            content.append(f"# {skill_name}\n\n{skill_content}")
    
    export_text = "\n\n---\n\n".join(content)
    
    if output_path:
        output_path.write_text(export_text)
        console.print(f"[green]Exported {len(skill_names)} skill(s) to {output_path}[/green]")
    else:
        # Print to stdout
        print(export_text)


@skills.command("install")
@click.argument("file_path")
def install_skill(file_path: str):
    """Install a skill from a file."""
    source = Path(file_path)
    if not source.exists():
        console.print(f"[red]file not found: {file_path}[/red]")
        raise SystemExit(1)
    
    content = source.read_text()
    
    # Try to extract name from frontmatter
    skill_name = source.stem
    if content.startswith("---"):
        try:
            end = content.index("---", 3)
            frontmatter = content[3:end]
            for line in frontmatter.strip().split("\n"):
                if line.startswith("name:"):
                    skill_name = line.split(":", 1)[1].strip()
                    break
        except ValueError:
            pass
    
    # Write to skills directory
    from ..skills import SKILLS_DIR
    dest = SKILLS_DIR / f"{skill_name}.md"
    dest.write_text(content)
    console.print(f"[green]Installed skill: {skill_name}[/green]")
