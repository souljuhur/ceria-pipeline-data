import os, shutil
base = r"d:\머신러닝 교육\ceria_pipeline_data"

files_to_remove = ["run_post_pipeline.py"]
files_to_move   = [("repair_excel.py", "utils/repair_excel.py"),
                   ("run_download_extra.py", "utils/run_download_extra.py")]

for fname in files_to_remove:
    p = os.path.join(base, fname)
    if os.path.exists(p):
        os.remove(p)
        print(f"삭제: {fname}")
    else:
        print(f"없음: {fname}")

for src_name, dst_rel in files_to_move:
    src = os.path.join(base, src_name)
    dst = os.path.join(base, dst_rel.replace("/", os.sep))
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"이동: {src_name} → {dst_rel}")
    else:
        print(f"없음: {src_name}")

print("\n=== 루트 .py ===")
for f in sorted(os.listdir(base)):
    if f.endswith(".py"):
        print(" ", f)

print("\n=== utils/ .py ===")
for f in sorted(os.listdir(os.path.join(base, "utils"))):
    if f.endswith(".py"):
        print(" ", f)
