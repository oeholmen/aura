import os

def export_source(output_path, max_size_mb=25):
    cwd = os.getcwd()
    total_size = 0
    with open(output_path, "w", encoding="utf-8") as out:
        for root, dirs, files in os.walk(cwd):
            # Exclude virtual environments, git objects, build directories, and artifacts
            if any(x in root for x in [".git", "venv", "__pycache__", "build", "dist", "node_modules", ".venv", ".pytest_cache"]):
                continue
            
            for f in files:
                if f.endswith((".py", ".md", ".json", ".js", ".html", ".css", ".spec", ".yaml", ".yml", ".toml", ".sh", ".txt")):
                    filepath = os.path.join(root, f)
                    try:
                        # Skip large files > 1MB directly
                        if os.path.getsize(filepath) > 1024 * 1024:
                            continue
                            
                        with open(filepath, "r", encoding="utf-8") as infile:
                            content = infile.read()
                            
                        header = f"\n\n{'='*80}\nFILE: {os.path.relpath(filepath, cwd)}\n{'='*80}\n\n"
                        out.write(header)
                        out.write(content)
                        total_size += len(header) + len(content)
                        
                        if total_size > max_size_mb * 1024 * 1024:
                            out.write("\n\n[WARNING: SIZE LIMIT REACHED, EXPORT TRUNCATED]")
                            print(f"Warning: Reached {max_size_mb}MB limit. Truncating.")
                            return
                            
                    except Exception as e:
                        out.write(f"\n[Error reading file {f}: {e}]\n")

if __name__ == "__main__":
    desktop_path = os.path.expanduser("~/Desktop/Aura_Source.txt")
    print(f"Exporting source code to {desktop_path}...")
    export_source(desktop_path)
    print("Export complete.")
