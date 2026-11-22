"""같은 실물 사진에 관절 상태만 바꿔 넣어 칸 선택이 따라 바뀌는지 (11-22). 상태 지름길 확인용."""
import json, os, sys, glob, numpy as np, torch, cv2
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors
root=os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_450")
ds=LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log={r["episode_index"]:r for r in map(json.loads, open(root+"_collection_log.jsonl"))}
S=np.stack(ds.hf_dataset.with_format("numpy")["observation.state"]); A=np.stack(ds.hf_dataset.with_format("numpy")["action"])
fr,to=list(ds.meta.episodes["dataset_from_index"]),list(ds.meta.episodes["dataset_to_index"])
lay=["-".join(log[e]["layout"][k][0].upper() for k in "123") for e in range(len(fr))]
states={L: S[[fr[e] for e in range(len(fr)) if lay[e]==L]].mean(0) for L in ["S-B-R","B-R-S","R-S-B","B-S-R","R-B-S"]}
states["실물"]=np.array([2.4,-86.9,46.3,71.7,-1.5,15.9])
slot_c={s: np.mean([A[to[e]-1][:4] for e in range(len(fr)) if log[e]["target_slot"]==s],0) for s in (1,2,3)}
T={"R":"Move the gripper close to the pink rose.","B":"Move the gripper close to the blue flower.","S":"Move the gripper close to the yellow sunflower."}
IM={"1121_230956":"B-S-R","1121_230848":"S-B-R","1121_230141":"R-B-S","1122_150640":"B-S-R"}
ck=sys.argv[1]
pol=SmolVLAPolicy.from_pretrained(ck).to("cuda").eval(); pre,post=make_pre_post_processors(pol.config, pretrained_path=ck)
for name,truth in IM.items():
    p=glob.glob(os.path.expanduser(f"~/lerobot_flower/realframes_1121/{name}_*.jpg"))[0]
    im=torch.from_numpy(cv2.cvtColor(cv2.imread(p),cv2.COLOR_BGR2RGB)).permute(2,0,1).float()/255
    print(f"\n사진 {name} 실제 배치 {truth}  (칸 순서로 꽃 표시, 정답이면 {truth})")
    for sn,st in states.items():
        got=["?"]*3
        for f in "RBS":
            torch.manual_seed(0)
            with torch.no_grad():
                ch=post(pol.predict_action_chunk(pre({"observation.images.camera1":im,"observation.state":torch.from_numpy(st.astype(np.float32)),"task":T[f]})))[0].float().cpu().numpy()
            s=min(slot_c,key=lambda k: np.linalg.norm(ch[-1][:4]-slot_c[k])); got[s-1]=f if got[s-1]=="?" else got[s-1]+f
        print(f"   상태={sn:6s} → 모델이 본 배치 {'-'.join(got)}")
