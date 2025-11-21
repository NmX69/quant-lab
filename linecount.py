# linecount.py   (drop this in your project root and run: python linecount.py)

import pathlib

root = pathlib.Path('.')

py_files = list(root.rglob('*.py'))

total_files = len(py_files)
total_lines = sum(len(f.read_text(encoding='utf-8').splitlines()) for f in py_files)

print(f"Python files found : {total_files}")
print(f"Total lines of code: {total_lines:,}")