"""trial4 데이터의 그리퍼 값 분포 (11-22, VLA 전 그리퍼 닫기 검토용)."""
import glob
from pathlib import Path
import numpy as np, pyarrow.parquet as pq

root = Path.home() / "lerobot_data/parkjoonsang/flower_reach_trial4"
t = [pq.read_table(f, columns=["action", "observation.state"]) for f in sorted(glob.glob(str(root / "data/*/*.parquet")))]
for k in ("action", "observation.state"):
    v = np.concatenate([np.stack(x.column(k).to_numpy(zero_copy_only=False)) for x in t])[:, 5]
    print(k, "그리퍼 백분위 1/25/50/75/99:", np.percentile(v, [1, 25, 50, 75, 99]).round(1))
