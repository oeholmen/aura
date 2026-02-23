import os
import pathlib

def create_bundle():
    project_root = "/Users/bryan/.gemini/antigravity/scratch/autonomy_engine"
    desktop_path = "/Users/bryan/Desktop/Aura_Source_Bundle.txt"
    
    extensions = {'.py', '.js', '.css', '.html', '.sh', '.spec', '.md', '.json'}
    exclude_dirs = {'.git', '__pycache__', 'dist', 'build', '.venv', 'env', 'node_modules', '.gemini', '.agents', '.agent'}
    exclude_files = {'Aura_Source_Bundle.txt', 'create_source_bundle.py'}

    with open(desktop_path, 'w', encoding='utf-8') as bundle:
        bundle.write(f"AURA SOURCE CODE BUNDLE - {os.popen('date').read()}\n")
        bundle.write("="*80 + "\n\n")

        for root, dirs, files in os.walk(project_root):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                file_path = pathlib.Path(root) / file
                if file_path.suffix in extensions and file not in exclude_files:
                    try:
                        relative_path = os.path.relpath(file_path, project_root)
                        bundle.write(f"\nFILE: {relative_path}\n")
                        bundle.write("-" * (6 + len(relative_path)) + "\n")
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            bundle.write(f.read())
                        bundle.write("\n\n" + "="*80 + "\n")
                    except Exception as e:
                        print(f"Error bundling {file}: {e}")

    print(f"Successfully created source bundle at: {desktop_path}")

if __name__ == "__main__":
    create_bundle()
