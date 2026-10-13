"""디렉터리를 결정적인 zip 으로 묶는다: 파일 순서 정렬 · 시각 고정 · 권한 고정 → 같은 입력이면 같은 해시.

python3 pack.py <src_dir> <out.zip>
"""
import os
import sys
import zipfile

FIXED = (1980, 1, 1, 0, 0, 0)
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_EXT = (".pyc", ".pyo")


def pack(src, out):
    files = []
    for root, dirs, names in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in names:
            if not n.endswith(SKIP_EXT) and n != ".DS_Store":
                files.append(os.path.join(root, n))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(files, key=lambda p: os.path.relpath(p, src)):
            info = zipfile.ZipInfo(os.path.relpath(path, src).replace(os.sep, "/"), FIXED)
            mode = 0o755 if os.access(path, os.X_OK) and path.endswith(".so") else 0o644
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(path, "rb") as f:
                z.writestr(info, f.read())
    return len(files)


if __name__ == "__main__":
    n = pack(sys.argv[1], sys.argv[2])
    print(f"packed {n} files -> {os.path.basename(sys.argv[2])}")
