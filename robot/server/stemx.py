import os, json, cv2, numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset
root=os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_450")
ds=LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log={r["episode_index"]:r for r in map(json.loads, open(root+"_collection_log.jsonl"))}
to=list(ds.meta.episodes["dataset_to_index"])
xs=[]; rows=[]
for e in range(ds.num_episodes):
    im=(ds[to[e]-1]["observation.images.front"].permute(1,2,0).numpy()*255).astype(np.uint8)
    hsv=cv2.cvtColor(im,cv2.COLOR_RGB2HSV)
    band=hsv[300:480]  # 아래쪽 = 줄기
    m=((band[...,0]>=30)&(band[...,0]<=85)&(band[...,1]>=70)&(band[...,2]>=60)).astype(np.float32)
    col=np.convolve(m.sum(0),np.ones(25)/25,"same")
    x=int(col.argmax()) if col.max()>20 else -1
    xs.append(x); rows.append((e,x,log[e]["task"].split()[-1][:-1],log[e]["target_slot"]))
xs=np.array(xs); ok=xs>=0
print("검출", ok.sum(), "/", len(xs))
print("줄기 x (화면 가로 640, 중앙 320): 중앙값", np.median(xs[ok]), "평균", xs[ok].mean().round(1), "p10/p25/p75/p90", np.percentile(xs[ok],[10,25,75,90]))
print("중앙(320)보다 오른쪽 비율", (xs[ok]>320).mean().round(2))
for name in ("rose","flower","sunflower"):
    v=np.array([x for e,x,t,s in rows if t==name and x>=0]); print(name, np.median(v))
for s in (1,2,3):
    v=np.array([x for e,x,t,ss in rows if ss==s and x>=0]); print("칸",s, np.median(v))
for a,b in ((0,90),(90,180),(180,270),(270,360),(360,450)):
    v=xs[a:b][ok[a:b]]; print(f"ep{a}-{b-1}", np.median(v))
json.dump({int(e):int(x) for e,x,_,_ in rows}, open(os.path.expanduser("~/lerobot_flower/stem_x_450.json"),"w"))
