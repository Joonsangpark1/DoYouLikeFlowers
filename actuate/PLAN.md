# actuate — 로봇팔 제어(SO-101) 모듈

## 역할
`observe`가 찾아낸 꽃의 대략적 위치와 `frontend` 레시피의 목표 배치(`target_slot`)를 입력받아,
SO-101로 해당 꽃을 집어(pick) 꽃병의 목표 위치에 꽂는(place/insert) 동작을 수행한다.
**학습 방법은 HIL-SERL(Human-in-the-Loop Sample-Efficient RL, Luo et al. 2024)을 그대로 채택한다.**
로컬 `~/lerobot`에 이미 HIL-SERL 구현체가 들어있음을 확인함(`docs/source/hilserl.mdx`,
`lerobot/rl/gym_manipulator.py`, `lerobot/rl/actor.py`, `lerobot/rl/learner.py`,
`lerobot/rewards/classifier/`) — 별도 설치/구현 없이 이 워크플로우를 그대로 따라간다.

## 왜 HIL-SERL인가 (이전 초안: ACT/Diffusion Policy 순수 모방학습 → 폐기)
- 꽃 집기는 contact-rich 작업(줄기 두께/각도가 개체마다 다르고, 힘 조절 실패 시 꽃이 손상됨)이라
  순수 모방학습보다 사람 개입으로 실패를 실시간 교정하며 학습하는 HIL-SERL이 적합
- 꽃병에 꽂기(insertion) 역시 HIL-SERL 논문이 강점을 보이는 대표 태스크 유형(커넥터 삽입류)과 구조가 같음
- 적은 데모 + 온라인 RL + 사람 개입으로 소수 시간 내 고성공률 도달 가능(모방학습 대비 데이터 요구량 낮음)

## 학습할 스킬 2개로 분리 (제안 — 사용자 확인 필요)
HIL-SERL 튜토리얼은 "5~10초 내 끝나는 단기 태스크"부터 시작할 것을 권장. 전체 pick&place를 한 번에
학습시키기보다 아래처럼 쪼개는 것을 제안한다.

1. **`flower_pick`**: 그리퍼가 꽃 근처 접근 지점에 위치한 상태에서, 줄기를 정밀하게 잡아 들어올리기
2. **`flower_place`**: 꽃을 쥔 상태로 꽃병 목표 슬롯 근처까지 이동한 상태에서, 기존 꽃들과 충돌 없이 정밀하게 꽂기

→ "탐색/대략 접근"은 스크립트(IK로 좌표까지 이동)로 처리하고, "마지막 수 cm의 정밀 동작"만 HIL-SERL로 학습시키는
하이브리드 구조. 이렇게 나누는 이유는 자유공간 이동은 RL이 필요 없는 쉬운 문제이고, RL 학습은 접촉이 발생하는
어려운 구간에 집중시키는 게 샘플 효율적이기 때문. (이 분리 기준 자체가 확정은 아님 — 실제로 해보고 한 번에
학습하는 게 더 잘 되면 합칠 수 있음)

## 워크플로우 (HIL-SERL 튜토리얼 순서 그대로)

### 1. 작업공간 bound 설정
- `lerobot-find-joint-limits`로 follower(SO-101)의 end-effector 안전 범위 측정
  - `flower_pick`용 bound: 꽃 트레이 중 "접근 완료 후" 반경(예: ±3cm) — observe의 좌표 오차를 흡수할 정도로만
  - `flower_place`용 bound: 꽃병 슬롯 근처 반경
- 결과를 `env.processor.inverse_kinematics.end_effector_bounds`에 반영

### 2. 데모 수집 (`mode: record`)
- 교시 장치: SO-101 leader arm 사용(문서상 SO101 leader는 기어비 덕에 추종이 부드러워 추천됨) 또는 게임패드
- 스킬별로 각각 `repo_id`를 나눠 `DATAS/lerobot_episodes/flower_pick/`, `.../flower_place/`로 수집
- 성공/실패는 키보드 `s`/`esc`로 라벨링 (LeRobotDataset에 reward로 기록)

### 3. 카메라 crop ROI 결정
- `lerobot.rl.crop_dataset_roi`로 워크스페이스만 남기도록 crop 설정 (배경 노이즈 제거 → RL 안정성 ↑)
- 해상도는 튜토리얼 권장대로 128×128 기본

### 4. Reward classifier 학습 (선택이지만 권장)
- `terminate_on_success: false`로 추가 성공 사례를 더 수집한 뒤, ResNet10 기반 CNN 이진 분류기 학습
- `flower_pick`용: "그리퍼가 꽃을 쥔 채 들어올림"을 성공으로 판정
- `flower_place`용: "꽃이 목표 슬롯에 안정적으로 꽂혀 있음"을 성공으로 판정
- 초기엔 사람이 게임패드/키보드로 직접 성공 버튼을 눌러도 되며, classifier는 이후 자동화 단계에서 도입

### 5. Actor-Learner 온라인 RL 학습
- `lerobot.rl.learner` + `lerobot.rl.actor`를 각각 프로세스로 실행 (SAC 기반)
- 사람은 게임패드/leader arm의 개입 버튼(`space`)으로 위험하거나 비효율적인 행동을 실시간 교정
- 개입 비율(intervention rate)이 학습이 진행될수록 감소하는지 wandb로 모니터링 — 이게 학습이 잘 되고 있다는 핵심 신호

## observe와의 인터페이스
- observe가 주는 것은 **월드 좌표계의 "대략적" 위치**(species/color 매칭된 후보 1개의 xy, 높이는 트레이 평면 가정)
- actuate 쪽 오케스트레이션 로직이 이 좌표로 스크립트 기반 pre-grasp 자세까지 이동 → 그 지점부터 `flower_pick`
  HIL-SERL 정책이 이어받음 (즉 observe는 "정밀 grasp point"를 줄 필요가 없고, HIL-SERL이 근접 오차를 학습으로 흡수)
- `flower_place`의 목표는 observe가 아니라 `frontend` 레시피의 `target_slot`에서 직접 가져옴

## 개발 단계
1. `lerobot-find-joint-limits`로 두 스킬의 EE bound 파악
2. `flower_pick` 데모 15~30 에피소드 수집 → crop ROI 결정
3. `flower_pick` reward classifier 학습(선택) → actor-learner 온라인 학습 → 성공률/개입률 확인
4. `flower_place` 동일 절차 반복
5. observe 좌표 → 스크립트 접근 → HIL-SERL 인수인계 오케스트레이션 코드 작성 (좌표계 캘리브레이션 선행 필요)
6. 두 스킬을 연결한 end-to-end 실행, 레시피 다중 아이템 순차 처리

## 미정 / 다음 논의 필요
- `flower_pick`/`flower_place`를 정말 분리 학습할지, 하나의 스킬로 합쳐도 되는지는 실험 후 재판단
- 스크립트 접근 구간과 HIL-SERL 구간의 경계(반경 몇 cm에서 인수인계할지) — observe의 좌표 오차 크기에 달려있어
  observe 캘리브레이션 정확도 측정 후 결정
- reward classifier를 종/색상별로 따로 둘지 공용 하나로 둘지 (꽃마다 grasp 성공 판정 기준이 크게 다르지 않다면 공용으로 시작)
