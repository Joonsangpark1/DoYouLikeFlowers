"""
데스크탑(GPU)에서 돌리는 원격 추론 서버. lerobot 공식 async_inference policy_server를 그대로 쓰되 한 가지만 패치한다.

패치: 이미지 리사이즈 끄기
  공식 서버는 로봇 이미지(640x480)를 정책 config의 이미지 크기(smolvla_base: 256x256)로 비율 무시
  bilinear 리사이즈한다. 그런데 학습 때는 데이터셋 원본(480x640)이 SmolVLA 내부에서 비율 유지 +
  패딩(resize_imgs_with_padding=512x512)으로 들어갔다. 서버에서 찌그러뜨리면 학습/추론 입력 분포가
  달라지므로, (H,W,C)->(C,H,W) 변환만 하고 크기는 그대로 넘겨서 정책 내부 전처리가 학습 때와 똑같이
  처리하게 한다.

실행 (데스크탑 WSL):
  conda activate lerobot
  python serve_policy.py --host=0.0.0.0 --port=8080 --fps=30
노트북에서 run_remote_policy.py로 접속한다. 모델 경로는 클라이언트가 보낸다 (서버 기준 경로).
"""
import torch

import lerobot.async_inference.helpers as helpers


def _keep_size(image: torch.Tensor, resize_dims) -> torch.Tensor:
    assert image.ndim == 3, f"Image must be (H, W, C)! Received {image.shape}"
    return image.permute(2, 0, 1)


helpers.resize_robot_observation_image = _keep_size

from lerobot.async_inference.policy_server import serve  # noqa: E402

if __name__ == "__main__":
    serve()
