"""시작 화면에서 꽃이 얼마나 보이는지 (11-22). 색 면적(화면 비율)과 가로 중심."""
import os, json, cv2, numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset
root=os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_450")
ds=LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log={r["episode_index"]:r for r in map(json.loads, open(root+"_collection_log.jsonl"))}
fr=list(ds.meta.episodes["dataset_from_index"])
def masks(im):
    h=cv2.cvtColor(im,cv2.COLOR_RGB2HSV); H,S,V=h[...,0].astype(int),h[...,1].astype(int),h[...,2].astype(int)
    return {"rose":((H>=160)|(H<=8))&(S>=60)&(V>=120), "blue":(H>=95)&(H<=125)&(S>=60)&(V>=90), "sunflower":(H>=15)&(H<=35)&(S>=110)&(V>=140)}
rows={}; grid={}
for e in range(len(fr)):
    im=(ds[fr[e]]["observation.images.front"].permute(1,2,0).numpy()*255).astype(np.uint8)
    L="-".join(log[e]["layout"][k][0].upper() for k in "123")
    for f,m in masks(im).items():
        a=m.mean(); xs=np.nonzero(m)[1]; cx=xs.mean() if len(xs) else -1
        slot=[log[e]["layout"][k] for k in "123"].index(f)+1
        rows.setdefault((L,f,slot),[]).append((a,cx))
    if L=="B-S-R": grid.setdefault(L,[]).append((e,im))
print(f"{'배치':6s} {'꽃':9s} 칸  보이는면적%(중앙값, p10)  가로중심px(중앙값)")
for (L,f,s),v in sorted(rows.items()):
    a=np.array([x[0] for x in v])*100; c=np.array([x[1] for x in v])
    print(f"{L:6s} {f:9s} {s}   {np.median(a):5.1f} {np.percentile(a,10):5.1f}        {np.median(c[c>=0]) if (c>=0).any() else -1:5.0f}")
sel=grid["B-S-R"][::11][:8]
tiles=[]
for e,im in sel:
    t=im.copy(); m=masks(im)["rose"]; t[m]=(0.5*t[m]+0.5*np.array([255,0,255])).astype(np.uint8)
    cv2.putText(t,f"ep{e}",(10,40),0,1.2,(255,0,0),3); tiles.append(cv2.resize(t,(320,240)))
g=np.vstack([np.hstack(tiles[i:i+4]) for i in (0,4)])
cv2.imwrite(os.path.expanduser("~/lerobot_flower/bsr_start_grid.jpg"),cv2.cvtColor(g,cv2.COLOR_RGB2BGR))
