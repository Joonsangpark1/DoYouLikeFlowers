# 꽃꽃이 로봇 — 진행 기록 (이어서 작업하기용)

> 작업할 때마다 이 파일 맨 위 "현재 상태"와 "작업 로그"를 갱신한다. 새 대화에서는 이 파일부터 읽고 시작.
> 마감: **2026-11-30 전시회 라이브 데모** → 일반화보다 정해진 시나리오에서 확실한 성공이 우선.
> 큰 설계 논의 원문: `decisions/2026-09-24.md`, 전체 흐름: `FLOW.md`, 파트별 계획: `observe/PLAN.md`, `actuate/PLAN.md`

---

## 2026-11-16 갱신: 그리퍼 교체 → 데이터 처음부터 다시 (trial3)
- 그리퍼 교체 후 **그리퍼만 재캘리브레이션** (임시 id `gripper_tmp`로 전체 캘리브레이션 → `merge_gripper_calib.py`로 그리퍼 항목만 병합). homing 1758→1724, 범위 1342~2752 → 1257~2547 (폭 124°→113°). 팔 5축 그대로. 백업 `my_follower_arm_before_gripper_1116.json` (smolvla·hilserl 두 폴더). 다음 연결 때 lerobot이 물으면 ENTER (모터에 임시값이 써져 있음)
- 새 데이터셋 **`parkjoonsang/flower_reach_trial3`**: 꽃병 배치 3개 × 꽃 3종 × 30 = 270. 배치 = 회전 (1: sunflower/blue/rose, 2: blue/rose/sunflower, 3: rose/sunflower/blue — 꽃마다 각 칸 한 번씩). **11-16 18:08 정리**: 63개 중 61·62번(sunflower) 삭제 → 61개 (rose 30, blue 30, sunflower 1). 기록 파일 배치가 sunflower/rose/blue로 잘못 찍혀 있어 실제(2번칸 blue, 3번칸 rose)로 정정. 백업 `~/lerobot_data/parkjoonsang/flower_reach_trial3_backup_1116` + `..._collection_log_backup_1116.jsonl`. **18:43**: 91번째(episode_index 90, 배치2 첫 에피소드)가 sunflower로 찍힘 → `lerobot-edit-dataset modify_tasks`로 rose 정정 + 기록 파일 정정 (백업 `..._backup_ep90`). 원인: L로 배치 바꿀 때 순서 모드가 지시문을 안 바꾸던 버그 → 수정. 끊김 원인 = usbip 연결 리셋 (배터리 7.2 V 정상) → `usbipd attach --auto-attach` 로봇·카메라에 켜 둠. **20:40 원인 좁힘**: Windows에서 CH343·카메라가 동시에 사라짐 + 같은 때 "Power source change"(18:49/19:35/20:04/20:29) → 독(충전 겸용) 리셋 추정. 독은 게임패드 때문에 유지. 노트북 전원 설정 변경: 배터리 시 절전·화면끄기 3분→안 함 (되돌리기: `powercfg /change standby-timeout-dc 3; powercfg /change monitor-timeout-dc 3`). USB 선택적 절전·AC 절전은 원래 꺼져 있었음. 카메라 번호 바뀜 대비 `record_flower_reach.sh`가 /dev/v4l/by-id로 장치 찾음 배치 안 순서 rose 30 → blue 30 → sunflower 30. `record_dataset.py`에 `--order sequential` (한 꽃 다 차면 지시문 자동 전환), `--layouts` (쓸 배치만 지정) 추가. trial2는 옛 그리퍼라 섞지 않음
- 시작 자세(`start_pose.json`)의 그리퍼 값은 새 캘리브레이션 기준으로 다시 확인 필요

- **11-17 trial4로 처음부터 다시 수집** (`parkjoonsang/flower_reach_trial4`, trial3 183개는 보존): 새 시작 자세(어깨 들고 손목 72.6°), **손목 회전 캘리브레이션 기준점 180° 이동** (homing_offset 1528 → −520, `shift_wrist_roll.py`, 같은 자세 +179.1° → −0.9° 확인, 손목 회전 레지스터만 씀). 팀 공통 파일 2곳 + 설치본 동기화, 시작 자세 roll 179.21 → −0.79. 백업 `*_before_rollshift_1117.json`. trial3과 손목 회전 숫자가 180° 다르니 섞지 말 것
- **11-17 18:11 trial4 234개(12,677프레임) SmolVLA 학습 시작** (sior, `smolvla_trial4_1117_1811`, batch 32, 10000 step, 약 31분, mem 5.5 GB, 로그 `~/lerobot_flower/train_1117_1811.log`). 데이터는 Windows scp로 복사 (WSL에서 ssh로 바로 보내면 멈춤). GPU 비우려고 로보틱스2 img_prior_v1을 89.5만 step에서 중단. **18:43 완료, 최종 loss 0.055** (trial3 0.051과 비슷), 체크포인트 2000~10000 + last
- **11-18 trial4 오프라인 검증** (`~/lerobot_flower/eval_trial4.py` = eval_trial3과 같은 기준 + STATE_MODE, 결과 `logs/eval4_*.txt`). 사진은 각 에피소드 첫 프레임, 지시문 3개씩, 234개 전부:
  | 시작 상태 | 꽃 고르기 | 정답 지시문 | 바꾼 지시문 따름 | 궤적 오차 |
  |---|---|---|---|---|
  | 에피소드 첫 프레임 (trial3 방식) | 85% | 99% | 78% (원래 꽃 14%) | 3.1° |
  | start_pose.json (실물 시작 자세) | 66% | 87% | 55% (원래 꽃 27%) | 6.2° |
  | **trial4 첫 프레임 평균** | **92%** | 99% | **88%** (원래 꽃 6%) | 3.1° |
  trial3(바꾼 지시문 32%) 대비 섞어 모으기 효과 확인. 발견: 녹화 첫 프레임 팔꿈치가 start_pose.json보다 평균 +8.1° (최대 12°, 토크 풀면 처짐) → 실물에서 start_pose.json에 세우면 학습에 없던 상태라 66%로 떨어짐. 에피소드별 첫 상태보다 평균이 더 좋은 건 첫 상태에 에피소드 정보(=정답 꽃)가 묻어 있어서로 보임. → **VLA 출발 자세를 평균으로 통일**: `smolvla_데이터수집/code/start_pose_vla_trial4.json` {pan 3.84, lift −84.67, elbow 41.49, wflex 72.08, roll −1.98, grip 15.71}, run_remote_policy.py(기본 모델도 trial4 last로, 백업 .bak_1118)와 record_prior.py 기본값으로 지정. 녹화용 start_pose.json은 그대로
- **11-18 trial3 vs trial4 영상 품질 실측** (각 25 에피소드): 선명도(Laplacian 분산) 중앙 **trial3 7 vs trial4 188 (약 27배)**, 거의 같은 프레임 반복 8% vs 3%, 프레임 간 차이 11.1 vs 17.2. trial3 영상은 거의 흐릿한 수준 → 사용자 가설 "해상도/화질 해결이 성공 원인 중 하나" 지지. 단 섞어 모으기·시작 자세·에피소드 수도 함께 바뀌어 기여도 분리는 불가
- **11-18 Hugging Face 업로드 (비공개)**: `parkjoonsang/flower_reach_trial4` (234개), `parkjoonsang/flower_reach_trial3` (183개). collection_log.jsonl은 안 올라감 (로컬·sior에만)
- **11-18 16:44~16:50 실물 6회 (기록 켠 버전, 클램프 20°, 잘린 스텝 0%)** `D:\data\flower\policy_runs\1118_16*`. 배치가 **학습에 없던 배치**였음 (카메라 왼→오 = 칸1→3, 학습 영상으로 확인): 앞 5회 blue/sunflower/rose, 마지막 1회 rose/blue/sunflower. 결과: blue → 칸1 pan −13 (맞음), sunflower → 칸2 pan 3.5 (맞음), **rose 4회 모두 pan 6~8 = 칸2 (틀림, 정답 칸3·칸1)**. 칸 선택은 처음 2초 안에 결정되고, 이후 들어올림이 데모보다 덜 하고(lift −20 vs 데모 끝 −28~−33) 손목을 계속 꺾음(wflex −20~−41 vs −7~−9). 데모는 5.4초에 끝나는데 20초 동안 계속 움직임 → 도착 후 상태는 학습에 없음. rose→칸2는 배치 B(blue 칸1, rose 칸2)를 외운 것과 맞아떨어짐 (배치 암기 의심)
- **11-18 학습 데이터 라벨 확인**: 해바라기 데모 12개(배치별 4개) 화면 직접 확인 → 전부 해바라기 줄기로 감, 라벨 정상. 실물 s 실행도 실제로는 해바라기 줄기(칸2)에 도착했고, 옆 칸 수국이 앞을 가려 블루로 보였던 것
- **11-18 17:32 trial4 270개(16,028프레임) 재학습 시작** (sior tmux train, `smolvla_trial4_270_1118_1732`, 10000 step, batch 32, 약 32분, 로그 `train_1118_1732.log`). 추가 36개는 전부 배치3(R-S-B)을 90으로 채운 것 → 세 배치 각 90 (새 배치 4~6은 아직 0개). 서버 데이터 `~/lerobot_data/parkjoonsang/flower_reach_trial4_270` (234개 판은 `flower_reach_trial4` 그대로). 18:05 완료
- **11-18 270개 모델 검증** (`eval_trial4.py`에 EVAL_ROOT 추가, 결과 `logs/eval4_270_{mean,episode}.txt`):
  - 학습 사진(첫 프레임 평균 상태): 꽃 고르기 92%, 정답 지시문 96%, 바꾼 지시문 91%, 궤적 오차 4.4° → 234개 모델(92/99/88/3.1°)과 거의 같음
  - **학습에 없던 배치** (`eval_realframes.py`, 오늘 실물 실행 첫 사진 6장 × 지시문 3개, 칸 중심 pan −17.6/2.1/19.7): 234개 모델 6/18, 270개 모델 5/18 = 우연 수준. **지시문과 상관없이 거의 다 가운데 칸으로 예측** (맞은 건 가운데 꽃뿐). 같은 코드로 학습 사진 jpg 왕복 시 48/54라 코드 문제 아님
  - 결론: 학습한 3배치에서만 작동, 새 배치에선 꽃을 못 고름 (배치 암기). 배치3 보강은 효과 없음 → 새 배치 4~6(B-S-R, R-B-S, S-R-B) 수집 필요
- **11-21 새 배치 4~6 수집 시작 준비**: 로컬 trial4 270개 (배치1~3 × 꽃 3종 × 30) 확인. `record_flower_reach.sh` `--layouts`에 배치4 B-S-R / 배치5 R-B-S / 배치6 S-R-B를 1~3 뒤에 추가 (기존 기록 번호 유지, per-layout 90 그대로 → 목표 +270). `--resume` 하면 덜 찬 첫 배치(4)로 자동 시작
- **11-21 20:54 마지막 2개 삭제** (사용자 요청 "361·362번" = episode_index 360·361, 배치4 sunflower 2개): `lerobot-edit-dataset delete_episodes` → 362개/25,488프레임 → **360개/25,235프레임**, 기록 파일도 360줄로. 백업 `~/lerobot_data/parkjoonsang/flower_reach_trial4_backup_del1121` + `..._collection_log_backup_del1121.jsonl`
- **11-21 22:24 trial4 450개(32,039프레임) 재학습 시작** (sior tmux train, `smolvla_trial4_450_1121_2224`, batch 32, 10000 step, 로그 `train_1121_2224.log`). 배치 1~5 각 90 (꽃당 30), **배치6(S-R-B)은 0개**. 서버 데이터 `~/lerobot_data/parkjoonsang/flower_reach_trial4_450` (+`_collection_log.jsonl`), Windows scp로 복사. **22:58 완료, 에러 0, 최종 loss 0.095** (1K 0.238 → 5K 0.120 → 8K~10K 0.095~0.096에서 평평). 270개 모델 0.055보다 높음 — 같은 10000 step에 데이터가 2배라 에폭이 약 10 (270개 땐 약 20). 체크포인트 2000~10000 + last
- **11-21 23:01~23:10 450개 모델 실물 9회** `D:\data\flower\policy_runs\1121_23*` (사용자: "동작이 너무 이상"). 첫 화면으로 배치 확인: 1~7회 배치5 R-B-S, 8회 S-B-R(배치1), 9회 B-S-R(배치4) — 셋 다 학습한 배치
  - 칸 선택(끝 pan): 꽃마다 배치와 상관없이 rose −10~−13 / blue 2~4 / sunflower 14~18로 고정 → 배치5 7회 전부 맞음, 8회(sunflower→칸3 rose)·9회(blue→칸2 sunflower) 틀림 = 배치5에서 그 꽃이 있던 칸
  - 움직임: 클리핑 0%, 스텝 크기 데모 범위 안, 제어 주기 0.1초 정상. 대신 끝 자세 근처 도착까지 1~22초 (데모 길이 6.5~7.5초), 도착 후에도 계속 들어올리고(lift 최대 −15, 데모 끝 −28~−31) 손목을 위로 꺾음(wflex −15~−45, 데모 끝 약 −9) → 카메라가 꽃 위를 봄. 30초 또는 정지 키까지 안 멈춤 (11-18과 같은 양상)
  - 오프라인 (`eval_realframes_1121.py`, 오늘 첫 사진 9장 × 지시문 3): 배치5 사진 20/21, 배치1·4 사진 1/6. 학습 첫 화면 비교: 실물 화면에 보이는 **전원공급기(09.00 표시)가 학습엔 배치5 후반에만 있음** (배치5 ep360 20:56엔 없음, ep449 22:21엔 있음, 배치4 ep270·359엔 없음, 배치1은 배경이 아예 다름 11-17) → 배경으로 "배치5 장면"을 알아보는 지름길 가설. 전원공급기 가리고 다시 예측(`eval_mask.py`): 9회 사진 blue만 칸1로 맞게 바뀌고 rose·sunflower는 그대로 틀림, 배치5 사진 sunflower는 오히려 틀림 → 가린 효과 섞임, 가설 확인 안 됨. 같은 사진도 실행마다 칸이 바뀔 만큼 예측 흔들림(샘플링 노이즈)
- **11-21 데이터 증강 (사용자 선택: 배경 가리기 + 색/밝기 + 도착 후 정지 프레임, 좌우 반전은 안 함)**
  - 발견: SmolVLA loss가 에피소드 끝 뒤 행동을 `action_is_pad`로 빼서, 모델은 "도착하면 멈춤"을 배운 적 없음 → 도착 후 계속 움직이는 원인 후보
  - 정지 프레임: `sior:~/lerobot_flower/build_hold.py` (마지막 프레임 사진·상태·행동을 HOLD개 반복해 새 데이터셋). HOLD=20 (2초) → `~/lerobot_data/parkjoonsang/flower_reach_trial4_450_hold20`. 영상 재인코딩 차이 평균 0.7%. 버그 1회: add_frame이 task를 빼가서 재사용 프레임 에러 → lerobot이 image writer 기다리며 멈춤 (복사 후 add로 수정)
  - 이미지 증강: lerobot 내장 image_transforms, `aug_tfs.json` = 기본 6종(밝기·대비·채도·색조±0.05·선명도·회전±5°/이동5%) + CoarseDropout(최대 3개, 각 변 최대 40%, 검정). 한 사진에 3종 무작위. `train_smolvla.sh`에 `AUG=1` 옵션 추가 (백업 `.bak_1121`), 미리보기 `aug_grid.jpg`
  - **23:37 자동 학습 예약** (sior tmux `autotrain`): build_hold 끝나고 로그에 `done 450`이면 `AUG=1` + hold20 데이터로 `start_train.sh` 실행 (출력 `smolvla_trial4_450_hold20_aug_MMDD_HHMM`, batch 32, 10000 step, 로그 `train_MMDD_HHMM.log`). 실패하면 `autotrain_1121.log`에 BUILD_FAILED. 정지 프레임과 증강을 한 번에 넣어서 각각의 효과는 분리 안 됨
  - **11-22 원본 섞기 (다음 학습부터)**: lerobot은 사진마다 항상 7종 중 정확히 3종 적용(7C3=35 조합, 세기 연속 무작위) → 원본이 학습에 한 번도 안 나옴. 사용자 선택: 원본 20% + 나머지는 지금 세기. sior lerobot `src/lerobot/transforms/transforms.py`에 `ImageTransformsConfig.p_original`(기본 0 = 원래 동작) 추가 패치 (백업 `~/lerobot_flower/transforms.py.bak_1122`). `train_smolvla.sh`가 `P_ORIG`(기본 0.2) 전달. 검증: 0.0 → 원본 0%, 0.2 → 20.7%. Identity 3개 섞는 방식은 증강 세기가 43%→16%로 약해져서 안 씀. 11-22 14:41 이어서 학습 중인 모델은 원본 0% 그대로
  - **예약 실패**: build는 23:44 정상 완료(`done 450 41039`)했으나 `pgrep -f build_hold.py`가 대기 루프 자기 자신(명령줄에 같은 글자)을 잡아 밤새 대기 → 학습 안 됨. **11-22 14:15 수동 시작** (`smolvla_trial4_450_hold20_aug_1122_1415`, 로그 `train_1122_1415.log`, 41,039프레임, 증강 켜짐 확인, step 200 loss 0.260)
  - 14:39 step 7006에서 tmux `train` 세션째 종료 (에러·OOM 흔적 없음, 수동 종료로 보임) → **14:41 6000부터 이어서** (`lerobot-train --config_path=<ckpt>/last/pretrained_model/train_config.json --resume=true`, 로그 `train_1122_resume.log`, 데이터 순서도 epoch 4 sample 27776부터 복원). 6000 시점 loss 0.097
  - **14:54 완료**, loss 8K 0.089 / 9K 0.086 / 10K 0.089 (증강 없는 450개 모델 0.095와 비슷)
  - 실물 첫 사진 9장 × 지시문 3 (`logs/eval_rf1121_hold_aug.txt`): **22/27** (증강 없는 450개 모델 21/27). 배치5 사진 21/21, 배치1·4 사진 1/6로 이전과 같음 (배치4 사진 blue→칸3 pan+26, rose→칸1). 정지 동작은 이 평가로는 알 수 없음 (끝 자세 칸만 봄)
  - **11-22 상태 지름길 확인** (`st.py`, `st_swap.py`, 결과 `logs/st_swap_1122.txt`): 에피소드 첫 관절 상태만으로 배치 71% 맞춤 (우연 20%, 배치별 평균 차이는 1° 안팎, 표준편차 pan 0.97 / lift 0.65 / elbow 1.51 / wflex 0.24 / roll 0.84). 같은 실물 사진에 상태만 배치별 평균으로 바꾸면 고르는 칸이 바뀜 (예: 배치5 사진 + 배치3 상태 → R-S-B, 배치4 사진 + 배치5 상태 → R-B-S = 상태의 배치를 따라감). rose는 거의 항상 1번칸. → **사진보다 1° 미만 관절 상태 차이로 배치를 고르는 지름길** 가능성 큼
  - **11-22 15:11 상태 노이즈 학습 시작** (`smolvla_trial4_450_hold20_aug_snoise2_1122_1511`, 로그 `train_1122_1511.log`): hold20 데이터 + 증강 + 원본 20% + **관절 상태 가우시안 노이즈 std 2°** (sior `lerobot_train.py` 패치, 환경변수 `FLOWER_STATE_NOISE_STD`, `start_train.sh`의 `STATE_NOISE`로 전달, 백업 `~/lerobot_flower/lerobot_train.py.bak_1122`). 학습 루프에만 적용, 평가·추론엔 없음. 확인: 프로세스 환경 FLOWER_STATE_NOISE_STD=2, p_original 0.2, step 200 loss 0.367. 판정 기준: `st_swap.py`에서 상태를 바꿔도 칸이 안 바뀌고 사진대로 고르면 성공
  - **15:46 완료**, loss 2K 0.194 → 10K 0.104. `st_swap` (`logs/st_swap_snoise2.txt`): **상태를 바꿔도 출력 불변 (상태 의존 제거 확인)**. 그러나 사진 4장 중 3장에서 배치와 무관하게 항상 R-B-S로 답함 (1122 사진만 RB-S-?). 실물 사진 10장 (`logs/eval_rf_snoise2.txt`): 24/30 — 배치5 21/21, 배치1·4 3/9 (1122 사진 blue·sunflower 맞음). → 상태 지름길은 끊었지만 대신 지시문만 보고 꽃→칸 고정(R1·B2·S3)으로 감, 사진으로 꽃 위치를 거의 안 씀. 학습 첫 화면 평가(eval_trial4, mean 상태)로 학습 사진에서도 그런지 확인 중
  - **학습 첫 화면 평가** (eval_trial4, 450 데이터, 3개 간격 150 에피소드 × 지시문 3, mean 상태, `logs/eval4_450train_*.txt` — tail -25로 저장해 배치2 행 2개 잘림): 바꾼 지시문 따름 **노이즈 89% vs 노이즈 없는 450 모델 80%**, 정답 지시문 75% vs 74%. → 학습 사진에선 사진을 씀. 약한 곳: **배치4 B-S-R의 rose(3번칸) 2/30 vs 0/30** (오늘 실물 실패와 같은 조합, 예측은 가운데 sunflower로), 배치5 sunflower 18 vs 24, 배치3 R-S-B blue 29 vs 12, 배치1 S-B-R sunflower 25 vs 2 (노이즈로 크게 개선). 실물 사진은 학습 사진보다 훨씬 나쁨 → 실물 장면 차이(배치1은 11-17 다른 배경) + 특정 조합 약점 둘 다
  - **시작 화면 꽃 가시성** (`vis.py`, `logs/start_visibility_1122.txt`, 색 면적 = HSV 범위 픽셀 비율): 배치4 B-S-R의 rose(3번칸) **3.9% (p10 1.8%)로 15개 조합 중 가장 작음** (나머지 6~17%). 사진 확인(`bsr_start_grid.jpg`): 가운데 해바라기가 크고 오른쪽으로 기울어 rose를 가리거나 rose가 오른쪽 끝에 걸림. 또 11-21 장면엔 **분홍 테이프 롤(매트 위)·선반의 분홍 물건이 rose와 같은 색**으로 잡힘. 에피소드마다 시작 화면 각도도 꽤 다름 (ep314는 해바라기가 화면 절반)
  - 배치2 B-R-S (사용자 요청, `start_grid_B-R-S.jpg`, 평가 전체본 `logs/eval4_450train_snoise2_full.txt`): 면적 blue 12.7 / rose 10.2 / sunflower(3번칸) 6.9% (p10 5.2), 노이즈 모델 학습 사진 blue 30/30, rose 29/30, sunflower 27/30. 세 꽃 다 보이고 3번칸 해바라기는 오른쪽 끝에 반쯤 걸려도 맞춤. 이 장면(11-17)에도 분홍 작은 물건들 있음. ep90은 장미가 화면 1/4을 차지할 만큼 가까움
  - **11-22 시작 자세 후보 캡처** (`smolvla_데이터수집/code/capture_start.py` 새로 작성: 토크 끄고 손으로 옮김 + Enter 저장, 미리보기에 꽃 색 면적 실시간. 저장 `D:\data\flower\start_pose_candidates\`). 배치4 B-S-R, 분홍 물건 치움. 4장: 00 현재 시작 자세(lift −86, elbow 46) rose 7.3 / blue 8.9 / sun 10.7%, 01~03 어깨 들고 팔꿈치 접음(lift −68~−90, elbow 28~41) rose 4.7~6.3 / blue 11.6~12.4 / sun 15.8~17.3%. **어느 자세든 양쪽 꽃(blue·rose)이 화면 가장자리에서 잘림**, 뒤로 뺄수록 가운데 해바라기만 커짐. 계산: 칸 간격 85mm(양끝 170mm), 시작 자세 손목 카메라 ~ 꽃까지 약 10cm → 세 꽃을 다 담으려면 카메라가 약 20cm 이상 떨어져야 함 (손목 카메라 화각 한계)
  - **11-22 16:16 꽃 정리 후 실물 (snoise2 last, rose)** `policy_runs/1122_161618_rose`: 배치4 B-S-R, 분홍 물건 치움. **pan 17.6 = 3번칸 rose 맞음** (같은 배치에서 15:06 hold_aug 모델은 1번칸으로 틀림). 약 9초에 도착, 이후 20초간 pan·lift 거의 고정(lift −17~−18), 손목만 −9 → −22로 천천히 꺾임, 팔꿈치 53 → 59 (이전 모델보다 표류 훨씬 적음). 끝 화면 줄기는 화면 중앙보다 오른쪽 (x 약 460)
  - 같은 배치4로 이어서: **blue** `1122_161741_blue` pan −15 = 1번칸 맞음, 약 10초 도착 후 끝까지 거의 고정 (끝 lift −29 / wflex −10 = 데모 끝 자세와 거의 같음, 마지막 화면에 사람 손이 줄기 잡고 있음). **sunflower** `1122_161842_sunflower` pan 0~1 = 2번칸 맞음, 고정 잘 됨 (lift −32~−36, wflex −11~−16). 단 sunflower는 기록 첫 상태가 시작 자세가 아님 (lift −68, elbow 65, wflex 36 — 첫 사진이 이미 해바라기 줄기 앞) → 시작 자세에서 출발 안 한 실행이라 칸 고르기 근거로는 약함. 배치4 3/3 (sunflower는 조건부)
  - **배치6 S-R-B (학습에 없음) sunflower** `1122_162022_sunflower`: 정답 1번칸(pan 약 −17)인데 **pan 2.5 → 3.4로 좌우로 안 돌고 그대로 앞(2번칸 rose)으로** 감 (사용자: "못 보는 것 같아"). 시작 화면: 해바라기 왼쪽 끝에 반쯤, 가운데 장미 크게, 파랑 오른쪽 위. 도착 5초, 이후 고정 잘 됨 (lift −27, wflex −10~−15)
  - **11-22 사용자 결정: 배치6 추가 수집** (꽃당 30 = 90개 권장, `record_flower_reach.sh --resume`이면 배치6부터 시작). 장면 지름길 방지로 **수집하면서 배경(책상 물건·조명 등)을 계속 바꾸기로** (사용자 제안). 꽃 색과 같은 물건은 꽃 근처 금지, 로봇·꽃병 받침·카메라는 고정. 이후: 확인 → sior 복사 → 정지 프레임 → 재학습(상태 노이즈 + 증강 + 원본 20%)
  - **11-22 17:45 배치6 수집 완료 → 540ep** (6배치 × 꽃3 × 30, 37,460프레임, 로그와 일치). sior `~/lerobot_data/parkjoonsang/flower_reach_trial4_540` 복사. `~/lerobot_flower/chain_540.sh`(tmux `hold540`): build_hold HOLD=20 → `flower_reach_trial4_540_hold20` → 자동으로 학습 `smolvla_trial4_540_hold20_aug_snoise2_<시각>` (STATE_NOISE=2 시작자세/관절 노이즈, AUG=1, P_ORIG=0.2, 10000 step, batch 32 — 450 snoise2 모델과 데이터만 다름). 로그 `~/lerobot_flower/chain_540.log`. hold 완료 540ep 48,260프레임, **18:02 학습 시작** (`smolvla_trial4_540_hold20_aug_snoise2_1122_1802`, 로그 train_1122_1802.log, ~33분). 18:36 종료 loss 0.110
  - **11-22 540 모델 평가** (`~/lerobot_flower/eval_540.sh` → eval_540.log; realframes에 1122_161618/161741(배치4)·162022/162113(배치6 S-R-B) 첫 사진 추가). 450 snoise2 → 540 snoise2:
    - 실물 사진 42문항: 30 → 32. 배치6 실물 6문항: 2 → 5 (162113 해바라기만 칸2). 배치4 실물 6문항: 4 → 3. 230848/230956(옛 세션)은 둘 다 여전히 대부분 틀림
    - 학습 사진(540 중 3개마다, 지시문 바꾸기 포함): 74% → 86%. 지시한 꽃으로 가는 비율 75% → 89%
    - 배치6 학습 사진: 450 모델 blue 0/30·rose 17·sunf 4 (본 적 없는 배치 → 일반화 안 됨 재확인) → 540 모델 28·30·30
    - 여전히 약한 곳: 배치4 장미 1/30(해바라기에 가림), 배치1(R-B-S) 해바라기 18 → 12/30
    - st_swap: 상태 바꿔도 예측 거의 같음 (상태 지름길 없음 유지)
  - **11-22 18:43~ 540 모델 실물** (배치6 S-R-B 가정, 끝 pan: 칸1≈-16 / 칸2≈+4 / 칸3≈+17). 해바라기 2/2(184341·184502 pan-16·-17), 블루 1/1(184645 +17), 장미 2/4(184608·184830 +4 맞음, 184731 -15 해바라기 칸, 184916 +17 블루 칸). 사용자 소감 "나쁘지 않은데?"
  - **11-22 사용자 결정: SmolVLA reach는 이 정확도(540 snoise2 모델)로 확정, HIL-SERL로 넘어감.** VLA 모델 = `smolvla_trial4_540_hold20_aug_snoise2_1122_1802/checkpoints/last` (record_prior.py 기본 모델 변경 완료, 백업 .bak_1122)
  - **11-22 19:10 C270 고정 카메라 설치**: 로봇 뒤 위쪽, 꽃병 3개 + 오른쪽 놓는 통(검은 원통, 입구 넓음)이 한 화면에. 기준 화면 `D:\data\flower\c270_view\reference_1122_1910.jpg`. 미리보기 `hilserl_시연수집/code/view_c270.py`(WSL, 5559 수신 → localhost:8081, 5초마다 latest.jpg). 송신 `camera_sender_windows.py --find c270 --port 5559 --exposure -5`
  - **11-22 19:30 독 연결 점검** (포트 부족으로 독 사용, `hilserl_시연수집/code/check_hw.py`): 배터리 모터 전체 7.6~7.7V, 22~23°C 정상. 로봇 busid 3-4 auto-attach. 손목 카메라 독에서 31 fps 정상. **그러나 독에 카메라 2대를 같이 꽂으면 먼저 켠 1대만 열림** (MJPG·15fps로 낮춰도, 순서 바꿔도 동일 → 독 USB 대역폭). 카메라 1대는 본체 포트로 옮겨야 함. 오후 VLA 중 2번 모터 무응답은 사용자 판단 배터리 원인
  - **11-22 20:04 작업 영역 측정** (measure_workspace.py → configs/flower_hil.json, 이전 .json.bak): min [0.075, −0.278, −0.001] max [0.398, **0.404**, **0.485**]. 비교(`ws_check.py`): VLA 시작 끝단 (0.19, −0.01, 0.17), 칸1 도착 y +0.05~+0.11 / 칸2 −0.03~+0.02 / 칸3 −0.12~−0.06, x 0.24~0.35, z 0.07~0.16, 통 (0.135, −0.234). → y max·z max가 필요 이상으로 넓음 (y +0.15 제안, z는 줄기 꽂힌 깊이 듣고 결정) → 사용자: 줄기 꽂힌 깊이 8.5 cm, 그리퍼 닫아도 화면 가리는 것 없음. **bounds 확정 min [0.075, −0.278, −0.001] max [0.398, 0.15, 0.30]** (z max = 도착 최고 0.16 + 8.5 cm + 여유 5 cm). 측정 원본 `configs/flower_hil.json.bak_measured_1122`
  - **11-22 사용자 요청: VLA 시작 전 그리퍼 조금 닫기** → record_prior.py `--vla-gripper` (기본 10.0, 음수=끔): 시작 자세의 gripper를 이 값으로 + VLA가 보내는 gripper 명령을 이 값으로 덮어씀. trial4 데이터 그리퍼는 행동 15.4 고정 / 상태 15.5~16.4 (0=닫힘). 주의: VLA는 15.4 모양의 손목 화면·상태로만 학습 → 실물에서 도착 정확도 바뀌는지 확인 필요
  - **11-22 record_prior.py 성공 뒤 추가 녹화** `--success-frames` (기본 15 = 1.5초): Y 누른 뒤 그 자리에 정지 액션으로 멈춘 채 15장 더 녹화, 전부 reward 1, 마지막만 done (0이면 예전처럼 Y 프레임만). 화면 상태 "SUCCESS HOLD k/15 (don't touch)". 실물 미검증
  - **11-22 record_prior.py 사용자 요청 2건**: ①그리퍼는 시작 자세에서는 원래 값(15.7), **Start 누르면 먼저 --vla-gripper(10)로 닫고 0.3초 뒤 VLA** ②**VLA 잘못 갔을 때 되돌리기** `rewind()`: VLA가 보낸 관절 명령 기록을 거꾸로 2배속 재생 (직선 복귀는 꽃병 쓸 수 있어서). VLA 중 B, 또는 시연 중 B(버리고 되돌아감) → 같은 꽃으로 다시. 첫 시험 폴더 flower_hil_prior_test(저장 에피소드 0, 임시 이미지만)는 삭제
  - **11-22 20:17 첫 실물 시험 에피소드 저장** (flower_hil_prior_test ep0: rose, 성공, VLA 11.2초 뒤 넘겨받기(takeover), 시연 36초). 사용자 지적: 그리퍼가 이동 끝에 닫힘 → `move_smooth(gripper_first=True)`로 시작 자세 이동 시 그리퍼 먼저 닫고(10) 팔 이동. 패드가 일반 USB 패드라 화면/안내를 버튼 번호로 (Y=1 B=2 A=3 X=4 LB=5 RB=6 LT=7 RT=8 Back=9 Start=10, pad_map.json). 백업 record_prior.py.bak_1122b
  - **11-22 그리퍼 재조립 (집게가 90° 틀어져 조립돼 있었음, 사용자가 다시 끼움, 캘리브레이션 파일은 그대로)**: 손으로 닫힘 원시 2542 (99.6), 끝까지 열림 원시 1236 (0, 범위 밖 21틱) → 캘리브레이션 범위 1257~2547과 맞음. **그리퍼 값 0 = 끝까지 열림(약 115°), 100 = 닫힘** (예전 코드 가정과 반대). → `wrist_ee.py`·`teleop_wrist.py` 닫기 = 값 증가로 수정 (백업 .bak_1122), record_prior `--vla-gripper` 기본 **60 = 약 45° 열림** (사용자 요청: 원래 열려 있던 그리퍼를 45°까지 닫고 시작). trial4 VLA 데이터 그리퍼 15.4 = 약 97° 열림. 확인 도구 grip_read.py(토크 안 건드림)/grip_probe.py/grip_torque.py. 중간에 첫 재조립(닫힘 1499, 열림 217)은 범위 밖이라 다시 조립함. 독이 재연결돼 busid 3-x → 4-x (로봇 4-4 auto-attach)
  - **11-22 사용자 요청: VLA 그리퍼 35° 열림** → `--vla-gripper` 기본 **69** (45°=60에서 줄임). 패드 표시 5~10번 → L1/R1/L2/R2/SELECT/START. record_prior.py: 저장된 에피소드 없이 멈춘 폴더는 시작 때 자동 삭제 (저장분 있으면 예전처럼 --resume 요구). 시험 중 그리퍼를 꽃 근처에서 69로 닫다가 닿아 64에서 멈춤 → 55로 풀어 둠 (녹화 때는 시작 자세에서 닫으므로 해당 없음)
  - **11-22 게임패드 점검** (`pad_raw.py`, 송신기 원본 JSON): 왼쪽 스틱·L2/R2·버튼 전부 OK, **오른쪽 스틱만 0 고정 → 패드 ANALOG 버튼(빨간 불) 꺼져 있었음**, 켜니 rx/ry −1~1 정상. 패드 재연결 시 ANALOG 꺼질 수 있으니 녹화 전 불 확인
  - **11-22 독이 30분 새 2번 끊겼다 재연결** (busid 3-x → 4-x → 3-x, teleop_wrist에서 termios I/O error). 로봇 WSL 연결을 `usbipd attach --wsl --hardware-id 1a86:55d3 --auto-attach`로 바꿈 (번호 바뀌어도 자동). 독 재연결 때마다 손목 카메라·게임패드 송신기 재시작 필요, 패드 ANALOG도 다시 확인
  - **11-22 독 또 재연결 (3-x → 4-x)**: hardware-id auto-attach도 처음 busid에 묶여서 못 따라감 → `hilserl_시연수집/code/reconnect.ps1` (지금 busid로 로봇 attach + 송신기 3개 재시작, UTF-8 BOM 필요)
  - **11-22 teleop "못 가는 곳이 너무 많음"** (`reach_check.py` 오프라인 IK): VLA 도착 자세에서는 숙임 고정으로도 앞·좌우·위 15 cm, 뒤 중앙 10 cm(최소 4, shoulder_lift 한계), 아래 15 cm → 녹화 시작 자세는 문제없음. 원인 추정: teleop이 **접힌 쉬는 자세(elbow 96.9° > URDF 한계 96°)에서 시작** → 거의 모든 방향 실패. teleop_wrist.py가 시작 때 VLA 시작 자세로 먼저 이동(그리퍼 69 먼저)하도록 수정 (`--start-pose none`이면 예전처럼). VLA 시작 자세에서는 뒤 5 cm·아래 6 cm까지만
  - **11-22 팔꿈치(3번) 모터 무응답 → 전원 껐다 켜서 복구.** 전압 7.6~7.7V(19:30) → **6.6~6.7V**(약 1.5시간 뒤, 충전 기준선). 저전압 순간 강하로 큰 관절이 멈추는 것으로 추정 (오후 2번 모터 무응답과 같은 증상) → 배터리 교체/충전 권함 → **배터리 교체 8.8~9.0V**, 모터 6개 정상. 교체 때 독이 또 재연결(4-x → 3-x) → reconnect.ps1로 복구. 로봇 전원 껐다 켤 때마다 독이 재연결되는 패턴으로 보임
  - **11-22 21:30 녹화 시험 3개 (사용자 "잘 된다", 이후 삭제)**: rose 성공(시연 29 s) / blue 성공(32 s) / sunflower 실패(시간 초과 30 s). **VLA가 3번 다 멈춤 판정 못 하고 15 s 시간 초과**로 넘어감. VLA 끝 pan: rose 5.3 / blue 13.8 / sunflower 6.8 — 배치 B-S-R이면 칸1(blue)≈−16·칸2≈+4·칸3(rose)≈+17이라 **rose·blue는 다른 칸으로 간 것으로 보임** (그리퍼 35°로 바꾼 영향 의심, 사용자 확인 필요). 사용자 요청: 시연 시간 30 → **60 s** (`--control-time-s`). 충전기를 독에 꽂자 독 인식 안 됨 → 본체로 되돌려 복구, reconnect.ps1은 로봇 확인 뒤 정리 + attach 뒤 5 s 대기로 수정
  - **11-22 독 또 리셋 (3-x → 4-x, 녹화 시작 때 /dev/ttyACM0 없음)** → `dock_watch.ps1` 새로 (3초마다 usbipd에서 로봇이 Attached 아니면 reconnect.ps1 자동 실행, 창 열어 둠). `camera_sender_windows.py`: 카메라 못 찾으면 바로 종료하던 것 → 2초 간격 최대 60초 재시도 (독 직후 실패 대책, smolvla 폴더 사본도 같게)
  - **11-22 사용자 보고: ANALOG가 처음엔 꺼져 있고, 누르면 저장됨** (일반 패드는 ANALOG 꺼지면 오른쪽 스틱이 버튼 1~4로 들어오고 전환 순간에도 버튼 신호가 튐 → 1 성공/3 실패가 저절로) → record_prior.py: ①1·2·3·4는 **0.4초 꾹** 눌러야 동작 (`held()`) ②프로그램 켠 뒤 오른쪽 스틱 아날로그 값(|rx| 또는 |ry| > 0.5)이 한 번 보이기 전엔 START 무시, 화면 "ANALOG? turn on + move RIGHT stick"
  - **11-22 21:43~ 시험 3개 (삭제)**: blue 성공 2(VLA 끝 pan 15.1·14.4, 시연 7.5 s·67.5 s), sunflower 성공 1(pan 5.3, 47 s). 전부 R1 넘겨받기(VLA 7.7~11.7 s). blue가 두 번 다 같은 pan +15로 가고 사용자가 성공 처리 → 앞서 "pan으로 보면 다른 칸" 의심은 내 칸-pan 대응 가정이 틀렸을 가능성 큼 (확인 안 됨)
  - **11-22 사용자: "VLA도 잘 못한다, 잘 안 되는 케이스도 기록하자"** → record_prior.py `log_vla_fail()`: 2번(되돌리기)을 누를 때마다 `~/lerobot_data/parkjoonsang/<repo>_vla_fail/`에 log.jsonl(꽃·지시문·배치·when=during_vla/after_vla·VLA 시간·VLA 멈춘 자세 q) + 그 순간 손목·C270 사진 저장. 데이터셋 폴더 밖이라 빈 폴더 자동 삭제에 안 걸림. after_vla 사진은 누른 순간 것(시연으로 팔을 움직였으면 VLA 끝 화면과 다름)
  - **11-22 사용자: "VLA 너무 별로" → 원인 확인: 그리퍼 상태 입력 분포 밖.** 540 hold20 학습 stats: observation.state 그리퍼 평균 15.9·**표준편차 0.2** (action 15.4·0.01). STATE는 MEAN_STD 정규화라 실제 그리퍼 69(35°)를 넣으면 z ≈ 265 → VLA 망가짐 (오후 실물 테스트는 그리퍼 안 바꿔서 정상). → record_prior.py `--vla-gripper-state` (기본 15.9): VLA 쪽 `robot.get_observation`만 감싸서 그리퍼 상태를 15.9로 바꿔 보여 줌 (실제 그리퍼는 69 유지, 녹화는 bus.sync_read라 영향 없음). 남는 차이 = 손목 화면 속 집게 각도. 실물 미검증. **교훈: 학습 때 거의 고정이던 입력(std 작은 차원)을 실행 때 바꾸면 정규화로 폭증**
  - **11-22 본 수집 시작** `parkjoonsang/flower_hil_prior` (WSL ~/lerobot_data/parkjoonsang/), 목표 30, 배치 blue,sunflower,rose. 설정: VLA 그리퍼 실제 69(35°)·VLA 입력 15.9, 시연 60 s, 성공 뒤 15프레임, 1~4 버튼 0.4 s 꾹, ANALOG 확인 게이트, VLA 실패 기록 `flower_hil_prior_vla_fail/`. 점검: 로봇 3-4 attached, 손목 32 fps·C270 30 fps, 패드·dock_watch·sior 서버 OK
  - **11-22 22:00 본 수집 1차 (사용자 요청으로 삭제)**: 성공 3 (blue pan 17 / sunflower pan −18 / rose pan 4.4), **VLA 실패 기록 20개 중 19개가 rose** (during_vla 대부분, 끝 pan 4~18). C270 사진: 실제 배치는 로봇 기준 왼쪽부터 **sunflower·rose·blue (배치6)** 인데 `--layout "blue,sunflower,rose"`로 잘못 기록됨. 블루 수국이 크게 퍼져 **장미 꽃송이를 거의 덮음** → 장미 가림이 주원인으로 추정 (배치4 장미 1/30과 같은 종류). 다음 실행 `--layout "sunflower,rose,blue"`, 블루를 벌려 시작 화면에서 장미가 보이게 하라고 안내. 실패 기록·사진·수집 로그는 지우기 전 `D:\data\flower\vla_fail_backup_1122\`에 백업
  - **11-22 22:20 손목 카메라 인식 실패 → 포트 교체**: 독(Prolific 허브 067B:2586)의 1·2번 포트에서 "Unknown USB Device (Port Reset Failed / Device Descriptor Request Failed)". 손목 카메라를 **본체(2-3)** 로 옮기니 정상 32 fps. C270을 독으로 옮겼더니 C270이 같은 오류 → 독 1·2번 포트가 카메라를 못 붙임 (로봇·패드가 꽂힌 3·4번 포트는 정상) → 사용자: 원래대로(C270 본체, 손목 독). 독에서 또 같은 오류 → pnputil 허브 재시작은 관리자 권한 없어 실패 → **독 케이블을 노트북에서 뺐다 꽂으니 정상** (손목 3-2 32 fps, C270 32 fps). 독 포트가 오류 상태에 걸리면 독 재연결로 풀림
  - **11-22 22:35 세션 종료.** 전압 **6.0~6.1V** (21:15 교체 직후 8.8~9.0V → 약 1시간 15분 만에 방전). HIL prior 데이터 0개 (전부 삭제). 사용자: "VLA도 잘 안 잡힘, 배터리 때문인지는 모르겠음". **VLA 정확도 저하 후보 (미분리)**: ①장미가 블루 수국에 가려짐 ②손목 화면 속 집게 각도 35° vs 학습 97° ③저전압으로 모터가 명령 자세를 못 따라감 → 상태·화면이 학습 궤적에서 벗어남 (그리퍼 상태 입력 문제는 `--vla-gripper-state 15.9`로 해결함). 다음에 한 번에 하나씩 분리: 충전된 배터리 + 꽃 안 겹치게 + `--vla-gripper -1`(그리퍼 학습 때처럼)로 VLA만 먼저 확인 → 그다음 그리퍼 35°
  - 사용자 (11-22): 시간 여유 있음, 모든 시간 투자 가능 → 천천히 원인 확인하며 가도 됨
  - **11-22 15:06 실물 1회 (hold20_aug last, rose)** `policy_runs/1122_150640_rose`: 배치 B-S-R (배치4, 학습함), 전원공급기 화면에 없음. rose(3번칸, pan ≈ +19)인데 **pan −13.5 = 1번칸 blue**로 감 (사용자: "꽃 인지 못한다"). 배치5 매핑(rose→1번칸) 그대로 → 전원공급기 없는 장면에서도 같은 실패라 배경 물체 가설 약해짐. 9.4초에 정지, 끝 자세 lift −30 / wflex −0.5 (데모 끝 −28~−31 / 약 −9에 가까움)
- **11-22 줄기 위치 치우침 (사용자 설계 의도)**: 데모는 그리퍼를 편 상태에서 줄기가 그리퍼 중앙에 오도록 모음. 그런데 접근할 때마다 줄기와 그리퍼가 닿아서 문제가 생김 → 도착 위치를 **아주 조금 좌측으로** 치우치게 하고 싶음. 증강 학습 결과 먼저 보고 해결하기로 함
  - 측정 (`sior:~/lerobot_flower/stemx.py`, 데모 마지막 프레임 아래쪽 초록 픽셀 기준, 대략값 → `stem_x_450.json`): 줄기 x 중앙값 417px (화면 640, 중앙 320), 81%가 중앙보다 오른쪽, 꽃·칸·시기 무관 380~470. 그리퍼 중심이 화면 몇 px인지는 아직 모름 (사진 필요)
  - 후보: ①실행 때 pan 보정 ②끝부분 행동 라벨 pan 보정 + 정지 프레임 사진 가로 이동 (px→도 비율은 데모에서 추정) ③목표선 그린 미리보기로 재수집
- **11-21 HF 업로드 (비공개)** `parkjoonsang/flower_reach_trial4` 234 → 450개로 갱신, `collection_log.jsonl`도 같이 올림. 이전 버전에서 남은 meta/episodes file-004~006 삭제 후 v3.0 태그 다시 붙임
- **11-17 HIL-SERL 고정 카메라 Logitech C270 구입**: Windows DSHOW index 1, 최대 1280x960, 자동 노출이면 640x480 15 fps → 노출 -5 고정으로 30 fps. 초점 고정, 화각 대각 약 55° (설치 위치 화면 확인은 아직)
- **11-17 HIL-SERL prior 시연 녹화 코드 `hilserl_시연수집/code/record_prior.py` (+ `record_prior.sh`, `wrist_ee.py`)**: 매 에피소드 시작 자세 → 서버 SmolVLA(trial4) 실제 실행 → 멈추면(1초간 관절 명령 변화 <0.5°, 2~15초) 그 자세에서 게임패드 시연만 녹화. 액션 [dx,dy,dz,droll,gripper] (사용자 선택: 손목 회전 추가, 숙임은 VLA 종료값 고정; xyz 0.8 cm/스텝, 회전 6°/스텝, 10 fps) → lerobot 공식 HIL-SERL actor는 4차원이라 actor도 wrist_ee.py를 써야 함. 카메라 2대: 손목 Innomaker(5558, VLA 입력 겸용) + 고정 C270(5559). 송신기 `camera_sender_windows.py --find innomaker|c270` (번호 대신 해상도 특성으로 찾음), smolvla attach_usb.ps1도 --find innomaker로 변경. RobotClient 하나를 에피소드마다 재사용(stub.Ready로 서버 상태만 초기화, 모델 재로딩 없음). 로그 `flower_hil_prior_collection_log.jsonl`(꽃·VLA 멈춘 이유·시간·종료 자세·결과). IK 오프라인 확인만 함 — 실물(로봇·Innomaker 연결) 테스트 아직
- **11-17 카메라는 WSL로 안 넘김 → Windows 송신기 방식**: 같은 카메라가 Windows 직접 29.7 fps / usbip 6~7 fps + 깨진 프레임 (WSL 재시작·버스 바꿔도 그대로). `camera_sender_windows.py`(Windows, JPEG를 localhost:5558로) + `net_camera.py`(WSL 수신, UsbipOpenCVCamera와 같은 read_latest 등) → WSL 수신 30.8 fps, 손상 0. `record_dataset.py --camera-source net`, `record_flower_reach.sh` 기본 net. `attach_usb.ps1`이 로봇만 WSL로 + 자동 재연결 + 카메라 떼고 송신기 실행 (`-CameraUsbip`로 예전 방식). 주의: 카메라가 WSL에 붙어 있으면 Windows index 0에 노트북 내장 카메라가 잡힘 → 송신기가 1080p 장치는 거부. HIL-SERL 폴더 스크립트/코드는 아직 usbip 카메라. **손목 회전 −179°가 ±180° 경계** → 넘어가면 시작 자세로 갈 때 한 바퀴 돎 (사용자: 기준점 이동은 보류)
- **11-17 카메라는 노트북 본체 USB에 직접** (독 X): 독에서는 영상 요청 순간 Windows "시스템에 부착된 장치가 작동하지 않습니다"로 끊김 반복(프레임 0). 본체 포트(busid 1-3)에서 5초 126프레임 = 25 fps, 실패 0 → 11-13의 "usbip 한계 약 11 fps"도 독 때문이었을 가능성. 데이터는 기존과 맞춰 10 fps 유지. 로봇은 독(3-4) 그대로. 자동 재연결 `usbipd attach --wsl --busid 1-3 --auto-attach`
- **11-17 수집 재개 설정**: 오프라인 검증 결과 trial3 모델이 지시문을 거의 안 따름 (정답 지시문 85%, 바꾼 지시문 32% = 우연 수준, 39%는 원래 에피소드 꽃으로) → 순서대로 모은 탓에 시간대 장면 단서로 꽃을 맞춘 지름길로 판단 (`sior:~/lerobot_flower/eval_trial3.py`). 남은 수집은 **섞어서(`--order balanced`)**, 저장·배치 변경 때 지시문이 추천 꽃으로 자동 전환. 109번 기록 배치2로 정정 (백업 `..._collection_log_backup_ep109.jsonl`). 현재 177개: 배치1 각 30 / 배치2 rose 31·blue 30·sunflower 26 / 배치3 0. 실물 확인(11-16 23:15~18 rose/sunflower/blue 각 20초)은 했으나 결과(어느 칸으로 갔는지) 미기록
- **11-16 22:24 SmolVLA trial3 학습 시작** (sior, tmux `train`): 177 에피소드 / 11,987 프레임 (서버 `~/lerobot_data/parkjoonsang/flower_reach_trial3`로 복사, HF 업로드 안 함), smolvla_base, batch 32, 10000 step, 2000마다 저장, 약 31분. 로그 `~/lerobot_flower/train_1116_2224.log`, 출력 `~/lerobot/outputs/train/smolvla_trial3_1116_2224`. 도착 오차 큰 7개(12,119,122,126,128,134,139) 포함된 채 학습
- 게임패드 조종: `hilserl_시연수집/code/teleop_wrist.py` 추가 (끝단 xyz + 손목 숙임 LB+오른쪽 스틱 + 회전 오른쪽 스틱 좌우, 자체 IK, 녹화 없음). lerobot 기본 경로는 방향 가중치 0.01 + 매 스텝 실제 FK 기준이라 손목이 흔들리고 처짐만큼 흘러감. WSL 실행 `~/run_teleop_wrist.sh`

## 현재 상태 (2026-11-13 기준)

| 항목 | 상태 |
|---|---|
| 데이터 | **HF `parkjoonsang/flower_reach_trial2` (비공개) 78 에피소드**, 10fps, 꽃 3종 (rose 32 / blue 30 / sunflower 16), 전부 배치 1번칸 sunflower·2번칸 rose·3번칸 blue. reach만, 그리퍼 고정. 에피소드별 배치 기록 `collection_log.jsonl` 같이 올림. 옛 `flower_reach`(5ep, 30fps, 재조립 전)는 안 씀 |
| 하드웨어 | 손목/그리퍼 재조립 → **재캘리브레이션 완료**, 새 시작 자세. 배터리 전원 (6.6V 아래면 충전, 11-13 오후 6.0V로 방전돼 팔꿈치 과부하 → 교체 후 8.8V) |
| 카메라 | WSL usbip 한계로 **약 11fps** → 10fps로 수집. 고정초점이라 가까우면 흐림. 가끔 0.5초 넘게 멈춤 (녹화 코드에서 처리) |
| 학습 서버 | **sior** (`ssh sior@100.101.102.84`, RTX 5080 16GB). 11-13 Tailscale 재로그인, HF 로그인 완료 |
| SmolVLA | trial2로 아직 학습 안 함 (sior `train_smolvla.sh`의 REPO_ID/OUT_DIR를 trial2로 바꿔야 함) |
| 그리퍼 패드 / 꽃병 | STL 설계 완료 (`Desktop\로보틱스\그리퍼_꽃병_설계`). **11-14 그리퍼 재캘리브레이션 완료** (`recenter_calibration.py --motors gripper`, 범위 119°, offset 1021→1781, range 2045~3446→1370~2724). 데스크탑 calibration 폴더 2곳 동기화 (이전본 `my_follower_arm_before_pad_1114.json`) |
| HIL-SERL | 시연 수집 도구만 있음 (가짜 로봇으로 검증), 실물 미검증 |

### 미결정 (사용자가 정할 것)
1. ~~HIL-SERL 꽂기(insert) 성공 판정: A 이미지 보상 분류기 vs B 꽃병 슬롯 물리 센서~~ → **11-22 결정: A 이미지 보상 분류기**
2. ~~HIL-SERL 정책 1개(잡기→꽂기) vs 2개(단계 분리)~~ → **11-22 결정: 정책 1개, 성공 = 줄기를 집어서 다른 통으로 옮긴 뒤 그 통에 놓은 장면** (분류기가 이 장면을 1로 판정)
3. dense shaping 섞을지 (제안: 안 섞음)
4. **탐색/접근 분리** (사용자 제안): 꽃 인식 방법 (색 / open-vocab / YOLO), VLA 지시문 유지 여부, 카메라 1개 vs 고정 카메라 추가
5. 수집 목표: 배치 6개 x 30 = 180 계획이었으나 첫 배치에서 꽃당 30개씩 모으는 중 → `--per-layout` 기준(30 or 90) 확정 필요
6. 핸드오프 설계(`decisions/2026-11-13_handoff.md`)용으로 시연에 그리퍼 닫기 포함할지

---

## 환경 / 접속 정보

### 노트북 (로봇 + 카메라 연결, Joony-Notebook)
- Intel Arc라 CUDA 없음 → 학습/추론 연산은 서버에서
- WSL 배포판 `Ubuntu`, conda `~/miniforge3`, env `lerobot` (`.[async]`), lerobot 커밋 `5aa74557`
- 커스텀 스크립트 `C:\Users\A\lerobot\`
  - `record_dataset.py` — 손 시연(토크 OFF) → 재생하며 녹화 → 저장/`--push`
  - `usbip_camera.py` — WSL usbip 카메라 (MJPG 640x480, 손상 프레임 버림, 미리보기 http://localhost:8080)
  - `check_dataset.py` — 추종오차/점프 점검
  - `run_remote_policy.py` — 원격 추론 클라이언트. **기본값이 sior로 바뀌어 있음** (원본: `run_remote_policy.py.bak_desktop`)
  - `start_pose.json` — 시작 자세
- Tailscale IP `100.119.83.72`

### sior (학습 + 추론 서버) — 2026-11-09부터
- `ssh sior@100.101.102.84` (노트북 `~/.ssh/id_ed25519` 키 등록됨, 비번 불필요)
- Ubuntu 24.04 네이티브 (WSL 아님 → portproxy 필요 없음), RTX 5080 16GB, RAM 60GB
- 공용 머신: IsaacLab 등 다른 conda env 있음 → 건드리지 말 것. sudo는 비번 필요
- conda `~/miniconda3`, env **`lerobot`** (py3.12, torch 2.11+cu130), `~/lerobot` 커밋 `5aa74557`, `.[smolvla,dataset,async]` + conda ffmpeg/tmux
- tmux는 env 안에만 있음: `~/miniconda3/envs/lerobot/bin/tmux` (비대화형 ssh PATH에 없음)
- 작업 폴더 `~/lerobot_flower/`
  - `train_smolvla.sh` — 학습 명령 (smolvla_base, `front → camera1` rename, batch 8, 3000 step)
  - `start_train.sh` — tmux 세션 `train`에서 학습, 로그 `train_MMDD_HHMM.log`
  - `serve_policy.py` — 공식 policy_server + 이미지 리사이즈 끄는 패치 (학습 때 비율유지 패딩과 맞춤)
  - `start_server.sh` — tmux 세션 `policy`로 추론 서버(포트 8080), 이미 떠 있으면 재실행 안 함
- 체크포인트: `~/lerobot/outputs/train/smolvla_flower_reach/checkpoints/{001000,002000,003000,last}`

### 자주 쓰는 명령
```bash
# 학습 (sior)
ssh sior@100.101.102.84 '~/lerobot_flower/start_train.sh'
ssh sior@100.101.102.84 'tail -c 500 $(ls -t ~/lerobot_flower/train_*.log | head -1)'

# 추론 서버 (sior)
ssh sior@100.101.102.84 '~/lerobot_flower/start_server.sh'
ssh sior@100.101.102.84 '~/miniconda3/envs/lerobot/bin/tmux attach -t policy'

# 로봇 실행 (노트북 WSL, conda activate lerobot, cd /mnt/c/Users/A/lerobot)
python run_remote_policy.py --task 1      # 1=핑크 장미, 2=노란 해바라기
python run_remote_policy.py --task 2 --model /home/sior/lerobot/outputs/train/smolvla_flower_reach/checkpoints/002000/pretrained_model
```
안전장치: 시작 자세로 천천히 이동, 스텝당 최대 10도 클리핑, ESC/Space 즉시 정지, 종료 시 토크 유지.

---

## 아키텍처 (확정된 것 / 검토 중)
- observe(느린 고수준 판단)와 actuate(저수준 제어) 분리 — 확정
- actuate = **SmolVLA**(자연어 지시문 기반 coarse reach) + **HIL-SERL**(정밀 grasp/insert) 하이브리드 — 검토 중
  - SmolVLA 도착 정확도를 재서 HIL-SERL 작업 영역(workspace bound) 결정하기로 함
- frontend: Vite+React+R3F, 12슬롯 꽃병 템플릿, 장미/카네이션/안개꽃 (`frontend/`, `npm run dev`)

---

## HIL-SERL 보상 설계 논의 (2026-11-09)

LeRobot 코드 확인: `reward_classifier`, `success_threshold`(0.5), `terminate_on_success`, `gripper_penalty` 지원.

- 기본: **sparse 이진 보상** (성공=1 → 에피소드 종료, 그 외 0) + 사람 개입 + 초기 시연. dense shaping 없이 가는 게 HIL-SERL 설계 의도
- 위험: 보상 오판정 → 정책이 오판정을 노림(reward hacking)
- **잡기(grasp)**: 그리퍼 관절 위치로 판정 (닫기 명령인데 끝까지 안 닫히고 멈춤 = 쥠) + 손목 높이 상승. 학습 불필요
- **꽂기(insert)**:
  - A. 이미지 보상 분류기 (ResNet10) — 추가 하드웨어 없음. 대신 성공 직전 실패 장면(옆에 꽂힘, 걸침, 쓰러짐)을 음성 데이터로 많이 모아야 함
  - B. 꽃병 슬롯 아래 리미트스위치/IR break-beam + 아두이노 — 거의 100% 정확, 전시 데모용으로 추천. 단 꽃병 개조 필요, 가벼운 줄기는 안 눌릴 수 있음
- 공통: SmolVLA 도착 지점 주변 박스로 행동 제한(벗어나면 0으로 종료), 10~20초 타임아웃, `gripper_penalty`는 0에서 시작

---

## 작업 로그 (최신이 위)

### 2026-11-16 — HIL-SERL용 자작 조이스틱 (사용자: VLA 다음 HIL 개입용, 아두이노/ESP32 둘 다 보유, 썸스틱 2개+버튼 방식)
- `hilserl_시연수집/code/joystick_fw/joystick_fw.ino`: Uno/Nano/ESP32 공용 (`#if defined(ESP32)`로 핀만 다름). gamepad_sender.ps1과 **같은 JSON 줄**(lx/ly/rx/ry/lt/rt/btn XInput 비트)을 시리얼 115200으로 60Hz 송신 → WSL `remote_gamepad`는 그대로
  - 버튼 INPUT_PULLUP(핀↔GND): 개입 RB / 성공 Y / 실패 A / 다시 X / Start / Back / 그리퍼 닫기 RT / 열기 LT. 선 빠지면 '안 누름' = 개입 꺼짐
  - 켤 때 스틱 가운데 자동 측정, 90%에서 풀스케일, 2샘플 디바운스, 개입 중 보드 LED. ESP32는 ADC1 핀만, 스틱 3.3V
  - arduino-cli(IDE 내장)로 nano/uno/esp32 컴파일 OK. **실물 보드·배선은 미검증**
- `code/serial_sender.ps1`: COM 자동 선택(로봇 CH343 제외) → TCP 5557 중계, 0.3초 무입력/USB 빠짐이면 `{"pad":-1}` → 로봇 정지, 재연결 자동. DTR/RTS 끔(ESP32 리셋 방지). 문법 검사만 함, 실행 미검증
- `attach_usb.ps1` 수정: 로봇을 이름 'CH34'로도 고르던 것 → CH343(1a86:55d3) 우선, CH340(7523) 제외. CH340 나노/ESP32 조이스틱을 같이 꽂으면 로봇 인식 실패하던 문제
- README 1장(부품·핀표)/2-2(serial_sender 실행) 추가
- **같은 날 실제 게임패드 연결**: XInput 아님 — 저가형 PS 모양 패드 `VID_0810 PID_0001` (DirectInput). ANALOG 불 꺼져 있으면 왼스틱 디지털(-1/0/1), 오른스틱이 면버튼 1~4로 나옴 → **ANALOG 켜야 함**
  - `code/pad_mapper.ps1` 새로 (안내 따라 하나씩 눌러 `pad_map.json` 저장), `gamepad_sender.ps1`에 winmm 일반 패드 fallback 추가 (XInput 없으면 pad_map.json으로 같은 JSON 송신)
  - 매핑 결과 `code/pad_map.json`: 4축 모두 아날로그 OK, ly=Y(-), lx=X(+), **ry=Z(-), rx=R(+)** (오른스틱 축이 보통과 반대), 버튼 R1=32 △=1 ○=2 ×=4 □=8 L1=16 L2=64 R2=128 SELECT=256 START=512
  - 임시 매핑+로컬 리스너로 sender 출력 형식 확인 OK. **WSL `gamepad_test.py`까지 끝단 확인은 사용자 사정으로 중단 → 다음에 이어서** (sender 켜고 gamepad_test.py로 방향/버튼 확인)

### 2026-11-15 — 녹화 시작 시 카메라 warmup 타임아웃 수정
- `record_flower_reach.sh --resume`가 `camera.connect()`에서 `TimeoutError ... after 1000 ms` (장치 /dev/video0 = Innomaker 맞음, v4l2-ctl 스트리밍 12~14fps 정상)
- 원인: 한동안 안 쓴 카메라를 처음 열면 첫 장 뒤 1초 넘게 멈춤 (연결 5회 중 첫 번째만 실패, 이후 16fps·최대 간격 0.07s)
- `smolvla_데이터수집/code/usbip_camera.py` warmup: 타임아웃은 넘기고 최대 warmup_s+5초 기다림 (`WARMUP_GRACE_S`). 수정 후 5회 연결 OK, 단 그때 카메라가 이미 깨어 있어서 **차가운 첫 연결 상황은 재검증 안 됨**

### 2026-11-13 — sior Tailscale 재연결 + 학습 전 점검
- sior가 2일간 offline → 서버가 다른 계정/로그아웃 상태였음 → `sudo tailscale up --force-reauth`로 joon9991 재로그인, IP 그대로 100.101.102.84
- 점검: SSH OK, RTX 5080 (policy 서버가 ~3GB 사용 중), 디스크 217G 남음, torch cuda OK, lerobot 5aa74557, HF 다운로드 OK
- sior HF 로그인 완료 (`parkjoonsang`, 11-13). 노트북 WSL도 parkjoonsang 로그인됨
- 데이터는 여전히 Hub/노트북 모두 flower_reach 5ep뿐 (10-04 이후 추가 수집 없음)
- **수집 시작하려다 막힘: wrist_roll(id 5) Overload** — Space(시작 자세 이동) 때마다 발생. 레지스터 읽어보니 goal 664(=-121.5°) / pos 1952(≈-8°)로 막혀 있었음.
  원인: 사용자가 손목/그리퍼를 **분해 후 재조립** → 같은 숫자(-121.5°)의 실제 방향이 바뀌어 케이블/기구에 걸림. 모터 자체는 정상(전압 6.9V, 온도 23~27℃, status 0)
  - 기존 5ep는 wrist_roll이 내내 -121.5° 고정. 카메라가 그리퍼에 달려 있어 손목 각도 = 화면 기울기
  - 예전 첫 프레임을 `Desktop\로보틱스\smolvla_데이터수집\예전_시작화면.png`로 저장
  - **다음(보류, 노트북 충전 후)**: attach_usb → setup_session → record 대기 상태에서 Z/Space 금지, T/G로 미리보기를 예전 화면 기울기에 맞춤 → ESC →
    wrist_roll 읽어서 `start_pose.json`의 wrist_roll만 수정 (smolvla_데이터수집/code + C:\Users\A\lerobot 둘 다)
  - **결정(사용자)**: 예전 5ep는 안 씀 → 새 데이터셋 **`parkjoonsang/flower_reach_trial2`**로 처음부터 수집. 옛 `flower_reach`(Hub+노트북)는 지우지 않고 보관
    - `smolvla_데이터수집`의 record_flower_reach.sh 기본 REPO_ID와 README를 trial2로 변경. 첫 녹화는 `--resume` 없이
    - 학습 시 sior `train_smolvla.sh`의 REPO_ID/OUT_DIR도 trial2로 바꿔야 함 (아직 안 바꿈)
- **재캘리브레이션 (11-13)**: 예전 데이터 안 쓰므로 새로 함. lerobot-calibrate 2번 다 가운데 자세가 어긋나 shoulder_lift/wrist_flex가 360° 랩어라운드
  → `smolvla_데이터수집/code/recenter_calibration.py` 새로 만듦 (관절을 끝에서 끝까지 움직이면 범위 가운데=2047로 offset/range 재계산, 파일+모터 기록. 패드 단 뒤 `--motors gripper`로 재사용)
  - 결과 범위: pan 212°, lift 194°, elbow 194°, wflex 209°, gripper 123° (원래 손가락 기준), wrist_roll offset 1462→936
  - 공용 캘리브레이션 두 폴더 갱신 (이전 것 `my_follower_arm_before_1113.json`), WSL 백업 ~/my_follower_arm_backup_1113.json
  - 옛 start_pose.json → `start_pose_before_1113.json` (새 캘리브레이션에선 무의미). `C:\Users\A\lerobot\start_pose.json`(원격추론용)도 옛 값 → 새 시작 자세 정해지면 동기화
  - 빈 trial2 폴더 삭제 (첫 녹화 때 --resume 없이 새로 생성)
  - **새 시작 자세** (손으로 잡아 저장하는 `save_start_pose.py` 새로 만듦): pan -22.0, lift -95.9, elbow 27.0, wflex 103.7, roll -0.1, grip 4.4
    → 범위 끝에 붙어 있어서 다시 저장 (save_start_pose.py에 카메라 미리보기 추가)
    **최종(19:59)**: pan -23.5, lift -87.7, elbow 29.4, wflex 90.7, roll -0.1, grip 4.6 → 끝까지 여유 lift 9.4° / wflex 13.5°, FK TCP (0.145, 0.046, 0.175) m
    `C:\Users\A\lerobot\start_pose.json`에도 복사 (옛 것 start_pose_before_1113.json)
  - URDF 0자세 = ㄱ자(위팔 수직, 아래팔·손목 수평 앞) 그림 `smolvla_데이터수집/캘리브레이션_기준자세.png`. FK가 맞는지(ㄱ자에서 관절값≈0) 아직 확인 안 함
- **카메라 fps 한계 발견 → trial2를 10fps로**: 첫 녹화에서 카메라 실제 11.6fps. 밝기/노출/동적프레임 바꿔도 10.7~12fps,
  v4l2 원본 스트림도 11.0fps(손상 0) → WSL usbip 전송 한계. 30fps 데이터셋엔 같은 프레임이 2~3번 반복 저장됨
  - 사용자 결정: 10fps로 녹화 (HIL-SERL도 10fps). `record_flower_reach.sh` 기본 `--fps 10`, 궤적 점프 검사를 속도 기준(450°/s ÷ fps)으로 변경
  - 30fps로 찍은 시험 에피소드는 `~/lerobot_data/_archive/flower_reach_trial2_30fps_test*`로 옮김 → trial2는 처음부터 (첫 실행 --resume 없이)
  - README 삭제 명령 수정: `lerobot-edit-dataset`은 `--new_root`를 `--root`와 같게 줘야 제자리 수정 (안 주면 ~/.cache에 따로 저장)
  - 대안(미착수): 카메라를 Windows에서 읽어 WSL로 송신하면 30fps 가능할 것
- **꽃 3종으로 확장** (사용자): pink rose / blue flower / yellow sunflower. `record_flower_reach.sh` 지시문 3개 + `--flower rose/blue/sunflower`
  - `record_dataset.py`에 꽃병 칸 배치 기록 추가: L 키로 6가지 배치 선택, 저장 시 `~/lerobot_data/parkjoonsang/flower_reach_trial2_collection_log.jsonl`에
    episode_index / task / layout / target_slot(1~3) 기록 + "가장 적게 모인 (꽃 x 칸) 조합" 추천. 실물 녹화로는 아직 미검증
  - 수집량 제안: 9조합(꽃3 x 목표칸3) x 조합당 ~10 = 약 90개 (파일럿 36개 먼저 → 학습/롤아웃 후 확대). 판단은 사용자
  - **수집 진행 (20:13~21:30경)**: 78개 (rose 32 / blue 30 / sunflower 16), 전부 배치 5 (1 sunflower, 2 rose, 3 blue).
    사용자 확인: 30·45번(rose 라벨)도 실제 rose로 감 → 라벨 전부 맞음
    - 사고 1: 종료 중 USB(usbip)가 빠져 프로세스가 커널 대기(D, usb_kill_urb)로 좀비화 → `kill -9` 안 됨 → `wsl --shutdown`으로 해결. 데이터는 finalize 끝난 뒤라 무사 (45ep, 영상 프레임 수 일치 확인)
    - 사고 2: 다시 켜면 지시문이 1번(rose)으로 돌아감 → 시작 시 현재 배치 추천 지시문으로 자동 설정 + `>>> 현재 지시문 <<<` 크게 표시로 수정
    - 사고 3: 팔꿈치(id3) Overload — 목표 29° / 실제 56°로 못 올라감. 원인: **배터리 방전 (6.9V → 6.0V)**. 교체 후 8.7~8.9V. 모터 전압 보호 4~14V, 모델 777(STS3215)
    - 사고 4: 시연 중 카메라 프레임 542ms 정체 → read_latest TimeoutError로 종료 (78ep는 finalize됨). 수정: 미리보기/대기/시연은 30초까지 허용,
      재생(=저장되는 구간)만 1초 넘게 멈추면 그 에피소드 버리고 다시 재생하게 (`REC_MAX_FRAME_AGE_MS`)
    - 표시 버그: per-layout 30(꽃당 10) 기준이라 `rose 31/10`처럼 보임 — 사용자가 꽃당 30개씩 모으는 중이라 기준 확인 필요
  - **학습 준비 (11-13)**: sior `train_smolvla.sh`를 환경변수로 바꿈 (기본 REPO_ID=trial2, batch 32, 10000 step, OUT_NAME=smolvla_trial2_날짜; 옛 것 .bak_1109),
    `start_train.sh`가 REPO_ID/OUT_NAME/STEPS/BATCH 전달. 시험 실행: batch 32에서 5.3 step/s(10k ≈ 31분), GPU 9.7GB(추론서버 3.2GB 포함) → 사용자가 직접 돌리기로 해서 1분 만에 중단·출력 삭제
  - **학습 완료 (사용자 실행, 21:46~22:18)**: `~/lerobot/outputs/train/smolvla_trial2_78ep/checkpoints/{002000..010000,last}` (sior). loss 1.12 → 0.030
    - 오프라인 점검 `~/lerobot_flower/eval_offline.py <ckpt>` (짝수 에피소드 첫 프레임, 정답 지시문 궤적 오차 + 지시문 3개 바꿔치기 → 예측 끝 자세가 어느 꽃 평균에 가까운지)
      | ckpt | 궤적 평균 오차 lift/wflex | 끝 자세 오차 lift/wflex | 바꿔치기 맞음 |
      | 4000 | 6.9 / 7.2° | 2.6 / 3.0° | 94/117 |
      | 6000 | 5.1 / 5.1° | 2.2 / 2.7° | 90/117 |
      | last(10000) | 3.4 / 3.4° | 1.4 / 1.6° | 93/117 (80%) |
      틀린 건 주로 sunflower 지시문 → rose로 감 (11~15회). sunflower 데이터가 16개로 적음. 실제 로봇 롤아웃은 아직
    - **HF 업로드**: `parkjoonsang/smolvla_flower_reach_trial2_78ep` (비공개, last=10000 step, 869MB)
  - **HF 업로드 (11-13)**: `parkjoonsang/flower_reach_trial2` **비공개**로 78ep 업로드 + `collection_log.jsonl`(에피소드별 배치/목표 칸). 공개 전환은 사용자 판단
  - **사용자 결정 (20:10)**: trial2 전부 삭제 후 새로 시작. **배치마다 30개(꽃당 10개) x 6배치 = 180개** 먼저, 이후 추가.
    첫 배치 1번칸 sunflower / 2번칸 rose / 3번칸 blue (= 배치 5). `--layout`, `--per-layout 30` 추가, 추천은 현재 배치 안에서 덜 모인 꽃 → 다 차면 다음 배치 안내
    (실제 녹화 1회로 jsonl 기록 동작 확인 후 삭제함)
- 사용자 제안: **탐색(베이스 돌리며 꽃 찾기)과 접근 분리**. 인식 방법(색 / open-vocab / YOLO), VLA 지시문, 카메라 수는 미결정. 손목 카메라는 고정초점이라 가까우면 흐림
- 핸드오프 설계 문서화: `decisions/2026-11-13_handoff.md` (사용자 설계 + 구현 간극 메모). 분석 스크립트는 착수 전 중단됨 (시작 자세 작업 우선)
- **넓은 그리퍼 패드 + 꽃병 설계** `Desktop\로보틱스\그리퍼_꽃병_설계\` (README, make_parts.py, stl/)
  - 원래 부품 재출력 없이 손가락에 씌우는 교체형 패드 (폭 40mm, 뒤 열린 U자, 손가락 뒤를 가로지르는 M2x30+너트 2개로 잠금). flat / stemV(가로 줄기 홈) 2종, 고정·움직임 쪽 한 쌍씩
  - 닫힐 때 두 접촉면이 평행하게 맞닿도록 설계 → 닿는 각도 URDF -8.5° (원래 손가락 끝 -11.3°) → 끝까지 닫으면 패드끼리 밀어서 과부하 가능
  - **11-14 수정 (사용자 요청)**: 고무판 1mm 자리 (`RUBBER_T=1.0`, 출력면을 1mm 뒤로, 미끄럼 홈 제거, stemV 홈 깊이 +1) → 고무끼리 닿는 각도 -6.9°.
    움직이는 쪽 패드 나사가 1개만 벽에 걸리던 버그 수정: 뒤쪽 절단 평면을 손가락 뒷면 두 점 대신 두 나사 중심 + 4mm로 → 양쪽 패드 나사 2개 모두 벽 안 (점검 통과)
  - 꽃병: 바닥 지름 80, 높이 80, 내경 12 + 깔때기 32, 바닥 무게추 홈. 3개 출력
  - **3구 꽃병** `flower_holder_x3.stl` (사용자 요청, 한 판): 210x70x80, 구멍 간격 70mm, 바닥 앞쪽에 칸 번호 점 1/2/3 (p_f 격자 칸 기록용)
  - **호 3구 꽃병** `flower_holder_arc3.stl` (사용자 요청: 호 모양 + 간격 넓게): 반지름 250 호, 간격 85 (19.6°), 250x90x80, 호 중심=로봇 베이스면 세 꽃 거리 동일. 도면 `도면_꽃병호3구.png`
  - 도구: CadQuery(STEP 읽기) + trimesh/manifold3d, venv `C:\Users\A\.venvs\cad`. 간섭 검사(전 열림 범위)·겹침 0 확인. **실물 출력/끼움 미확인**
  - **11-14 그리퍼 재캘리브레이션**: 처음엔 모터 6개 전부 응답 없음(포트 ACM0은 열림 → 전원/배선 문제), 해결 후 `recenter_calibration.py --motors gripper` → 범위 119°, offset 1781, range 1370~2724. 키보드 그리퍼 조작은 기존 `record_dataset.py` 대기 상태 y/h 키
  - **11-14 전체 재캘리브레이션 + 새 시작 자세**: s키(shoulder_lift −)가 안 먹던 원인 = 시작 자세가 lift 범위 끝 근처. recenter로 pan/lift/elbow/wflex/gripper 다시 (범위 pan 237°, lift 209°, elbow 195°, wflex 213°, gripper 124°), 데스크탑 calibration 2곳 동기화. 중간에 모터 5(wrist_roll) 응답 없음 → 재연결로 복구. 새 시작 자세 pan 9.76 / lift −91.21 / elbow 25.19 / wflex 93.14 / roll 58.33 / grip 0.64 (code/start_pose.json + C:/Users/A/lerobot/start_pose.json, 이전은 start_pose_before_1114.json). **캘리브레이션·시작 자세가 바뀌어서 기존 trial2 78ep와 관절값 기준이 다름**
  - **11-14 (이어서) 최종**: 손목 회전이 헛돎 → 그리퍼-혼 나사 풀림, 다시 조임. 이후 5관절 재캘리브레이션 (pan 243°, lift 210°, elbow 198°, wflex 217°, gripper 124°), wrist_roll이 0~4095 경계(raw 13)에 걸려 한쪽으로 못 돎 → 똑바른 그리퍼 방향을 0°로 Homing_Offset 936→1528 (범위 0~4095 유지). **최종 시작 자세** pan 11.6 / lift −87.5 / elbow 20.6 / wflex 92.0 / roll −1.0 / grip 16.3 (범위 여유 lift 17°, wflex 16°). code/start_pose.json + C:/Users/A/lerobot/start_pose.json, calibration 3곳 동기화 (이전 my_follower_arm_before_roll_1114.json)
  - **11-14 라벨 수정**: ep 122~130 (9개, 배치 rose/blue/sunflower)이 실제 rose인데 blue로 저장됨 → 프레임 task_index, 에피소드 메타 tasks/통계, stats.json, 배치 로그(target_slot 1) 전부 rose로 수정. 백업 `~/lerobot_data/parkjoonsang/backup_before_relabel_1114/`. 수정 후 133ep 8075프레임, rose 75 / blue 38 / sunflower 20. → 같은 날 HF 비공개 업로드 갱신 (133ep, collection_log.jsonl 포함, 허브에서 다시 받아 확인)
  - trial2 수집은 패드 단 뒤에 시작해야 함 (손목 카메라에 보이는 그리퍼 모양이 바뀜)

### 2026-11-11 — HIL-SERL 시연 수집 도구 (게임패드) `Desktop\로보틱스\hilserl_시연수집\`
- 공식 `lerobot.rl.gym_manipulator`의 make_robot_env/make_processors/step_env_and_process_transition 그대로 사용 → actor와 같은 데이터 형식
  (action `[dx,dy,dz,gripper]` -1~1 + 0닫기/1유지/2열기, next.reward, next.done, discrete_penalty, 10fps, 영상 원본 해상도)
- `lerobot_plugins.py`: config type `usbip_camera`(WSL 카메라+미리보기 상태 글자), `remote_gamepad`(TCP 5557 수신, 공식 GamepadTeleop과 같은 의미:
  RB 개입/Y 성공/A 실패/X 다시). WSL 커널에 xpad 없음 → 패드는 Windows `gamepad_sender.ps1`(XInput, 설치 불필요)이 localhost로 송신
- `record_demos.py`: 녹화 루프만 직접 (공식은 resume 불가·Ctrl+C시 finalize 안 됨·5초 고정 대기). Start로 에피소드 시작, 속도제한 복귀, always_intervene
  - 함정: `from __future__ import annotations` 쓰면 lerobot parser.wrap이 config 타입을 못 읽음
  - config의 env에 `"type"` 넣으면 draccus 에러 (env 필드가 HILSerlRobotEnvConfig 구체 타입)
- `measure_workspace.py`: 토크 끄고 손으로 훑어 EE bounds + Enter로 시작 자세 → config에 기록 (공식 find_joint_limits는 리더암 필요)
- `configs/flower_hil.json`: fps 10, step 0.01m, control_time 20s, max_relative_target 10, disable_torque_on_disconnect false, task 임시 "Grasp the flower stem."
- 검증: 가짜 로봇+스크립트 패드로 성공/다시/실패/시간초과/종료/resume 끝까지 OK, 왼스틱↑=+x, 왼스틱→=−y, 오른스틱↑=+z, RT→gripper 100.
  실제 sender(PowerShell)→WSL 수신 OK. **실제 로봇·실제 패드는 미검증** (특히 gripper 100이 실제로 닫힘인지 → 아니면 swap_gripper)
- 남은 것: crop ROI(공식 도구는 cv2 창 필요 → WSL 불가), actor 래퍼, 미결정 1~3번

### 2026-11-10 — 데이터 수집 가이드+코드 정리 (`Desktop\로보틱스\smolvla_데이터수집\`)
- 초보자용 `README.md` (개념 → 설치 → 세션 시작 → 녹화 → 점검 → 업로드/병합 → 문제 해결)
- `code/`: 노트북 `C:\Users\A\lerobot\`의 record_dataset/usbip_camera/check_dataset/feetech_ping_test/start_pose 복사
  - record_dataset.py: `--robot-port`, `--camera` 옵션 추가 (녹화 로직 변경 없음), feetech_ping_test: 포트 인자
  - 새 스크립트: `attach_usb.ps1`(CH343·Innomaker 자동 인식 bind/attach, 내장 카메라는 자동 선택 안 함),
    `setup_session.sh`(장치 확인·chmod·카메라 index0 노드 찾기·공용 캘리브레이션 설치), `record_flower_reach.sh`(지시문 고정)
  - `calibration/my_follower_arm.json`: 노트북 WSL 캘리브레이션 사본 (다른 사람이 재캘리브레이션하면 데이터 못 합침)
- 다른 PC 수집자는 각자 repo-id로 녹화 → `lerobot-edit-dataset --operation.type merge`로 병합하도록 안내
- 검증: WSL에서 setup_session.sh / record --help / check_dataset(기존 5ep) 실행 OK. 실제 로봇 연결 녹화는 안 해봄

### 2026-11-09 — sior로 이전 + SmolVLA 재학습
- 데스크탑 `irreplaceable-1`이 tailnet에서 사라짐 (오프라인 아님, 목록에 아예 없음) → **sior를 학습 서버로 쓰기로 결정**
- 노트북 SSH 키를 sior에 등록, conda env `lerobot` 새로 구축 (lerobot `5aa74557`, 노트북과 같은 커밋)
- 5ep / 3000 step / batch 8 재학습: 15 step/s, **약 3분** (4060 Ti 때 8분), 최종 loss **0.035**
- 체크 추론: 데이터셋 프레임 기준 예측과 실제 행동 차이가 관절당 1~3도, 추론 0.3초
- `serve_policy.py`를 sior로 옮기고 tmux `policy`로 실행, 노트북 Windows/WSL 양쪽에서 8080 접속 확인
- 노트북 `run_remote_policy.py` 기본 서버/모델 경로를 sior로 변경
- HIL-SERL 보상 설계 논의 (위 섹션)

### 2026-10-04 — 첫 데이터셋 + 원격 추론 end-to-end
- 수집 방식 확정: 키보드/IK가 어려워 **손 시연(토크 OFF) → 재생하며 녹화**. 리더 암은 안 삼
- HF `parkjoonsang/flower_reach` 5ep 공개 (task 1 `Move the gripper close to the pink rose.`, task 2 `... yellow sunflower.`)
- smolvla_base 카메라 키가 camera1~3이라 `front → camera1` rename 필요
- lerobot 기본 OpenCVCamera는 WSL에서 'Bad file descriptor' → usbip 카메라 전용 래퍼
- 데스크탑에서 학습 → async_inference 원격 추론 동작 (추론 0.27~0.38s)
- 공식 서버가 이미지를 비율 무시 256x256으로 줄이는 걸 끄는 패치 (`serve_policy.py`)
- 공식 클라이언트는 rename_map을 서버에 안 넘김 → 클라이언트가 처음부터 camera1로 보냄
- 로봇이 실제로 장미 쪽으로 갔는지는 확인 못 함

### 2026-09-24 — 아키텍처 논의 + 데스크탑 원격 인프라
- 상세: `decisions/2026-09-24.md`

---

## 다음 할 일 후보
- [ ] 로봇 연결 후 `run_remote_policy.py --task 1/2`로 실제 롤아웃, 장미/해바라기 쪽으로 가는지 관찰
- [ ] 지시문당 ~50ep 추가 수집 (꽃 배치 바꿔가며, 두 꽃 항상 같이) → sior에서 재학습 (steps 늘리기)
- [ ] SmolVLA 도착 정확도 측정 → HIL-SERL 작업 영역 결정
- [ ] HIL-SERL 미결정 사항 결정 후 구현
