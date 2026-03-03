import sys
from pathlib import Path

def validate_skill_file(file_path):
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return f"Could not read file: {e}"

    lines = content.splitlines()
    if not lines:
        return "File is empty"

    if lines[0].strip() != "---":
        return "Missing frontmatter (does not start with '---')"

    # Find the closing ---
    closing_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break

    if closing_idx == -1:
        return "Unclosed frontmatter (missing closing '---')"

    frontmatter = lines[1:closing_idx]
    has_name = any(line.startswith("name:") for line in frontmatter)
    has_description = any(line.startswith("description:") for line in frontmatter)

    errors = []
    if not has_name:
        errors.append("Missing 'name:' in frontmatter")
    if not has_description:
        errors.append("Missing 'description:' in frontmatter")

    if len(lines) <= closing_idx + 1:
        errors.append("Missing markdown content after frontmatter")

    if errors:
        return "; ".join(errors)
    
    return None

def main():
    root_dir = Path("/media/toni-sil/Arquivos3/agentes/.agent/skills")
    skill_files = list(root_dir.rglob("SKILL.md"))
    
    if not skill_files:
        print("No SKILL.md files found.")
        return

    print(f"Found {len(skill_files)} SKILL.md files. Validating...")
    
    has_errors = False
    for sf in skill_files:
        err = validate_skill_file(sf)
        if err:
            has_errors = True
            print(f"[{sf.relative_to(root_dir)}] -> {err}")
            
    if not has_errors:
        print("All SKILL.md files are valid and correctly formatted.")

if __name__ == "__main__":
    main()
