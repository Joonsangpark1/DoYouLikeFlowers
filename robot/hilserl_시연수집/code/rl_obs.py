"""HIL-SERL 강화학습 관측 전처리 (11-23). 오프라인 시연 변환(build_rl_dataset.py)과 실물 actor(flower_actor.py)가
**반드시 같은 함수**를 써야 함 (학습 때와 실행 때 사진이 달라지면 정책이 망가짐).

정책 입력 (사용자 결정 11-23: C270은 성공 판정에도 안 씀, 사람이 판정. 정책은 손목 카메라 + 관절만):
  observation.images.wrist  3x128x128  손목 카메라 640x480 → 가운데 480x480 정사각형 → 128x128
  observation.state         6          관절 6개 (도, 그리퍼 0 열림~100 닫힘)
행동: [dx, dy, dz, droll] (-1~1 연속) + gripper (0 닫기 / 1 유지 / 2 열기, 이산) = 5
"""
import cv2
import numpy as np

IMG = 128
WRIST_KEY = "observation.images.wrist"
STATE_KEY = "observation.state"
ACTION_DIM = 5          # 4 연속 + 그리퍼 1 이산
NUM_DISCRETE = 3        # 그리퍼 닫기/유지/열기


def preprocess_wrist(rgb: np.ndarray) -> np.ndarray:
    """RGB uint8 (H, W, 3) → RGB uint8 (128, 128, 3). 가운데 정사각형으로 잘라 비율 유지."""
    h, w = rgb.shape[:2]
    s = min(h, w)
    y0, x0 = (h - s) // 2, (w - s) // 2
    sq = rgb[y0:y0 + s, x0:x0 + s]
    return cv2.resize(sq, (IMG, IMG), interpolation=cv2.INTER_AREA)

# 11-25 사용자: C270(고정 카메라)도 정책 입력에 (꽃병 3개 + 통). 잘라내지 않고 화면 전체를 128x128로 (비율은 눌림, 학습·실행 같은 함수라 문제없음)
FRONT_KEY = "observation.images.front"


def preprocess_front(rgb: np.ndarray) -> np.ndarray:
    """C270 RGB uint8 (480, 640, 3) → RGB uint8 (128, 128, 3). 화면 전체를 줄임."""
    return cv2.resize(rgb, (IMG, IMG), interpolation=cv2.INTER_AREA)
