"""
SmolVLA에 넘길 자연어 지시문을 레시피(frontend가 저장한 DATAS/recipes/*.json)에서 생성한다.

핵심 제약(decisions/2026-09-24.md #5-4): 데모 수집 시 --dataset.single_task로 쓴 문구와
추론 시 --task로 쓰는 문구가 정확히 같은 템플릿에서 나와야 SmolVLA가 인식한다.
이 파일이 그 "단일 템플릿"의 소스 오브 트루스다 — 데모 수집 스크립트, 추론 스크립트,
향후 오케스트레이터가 전부 여기 함수만 호출해야 한다 (문구를 각자 하드코딩하지 말 것).

SmolVLA는 하이브리드 구조에서 "pick" 단계(넓은 시야 탐색 + 대략 접근)만 맡는다
(decisions/2026-09-24.md #4). place는 target_slot 좌표로 HIL-SERL이 처리하므로
자연어 지시문이 필요 없다 — 그래서 이 모듈은 pick 지시문만 다룬다.
"""

import json
from pathlib import Path

# 이 문구가 데모 수집/추론 양쪽에서 쓰는 유일한 템플릿이다. 바꾸면 기존 데모와
# 어휘가 어긋나므로, 데모 수집을 시작한 뒤에는 바꾸지 않는다(바꿔야 한다면 기존
# 데모를 폐기하고 새 템플릿으로 재수집).
PICK_INSTRUCTION_TEMPLATE = "pick the {color} {species_en}"

# flower_catalog.json은 species를 영문 slug(baby_breath 등)로만 갖고 있어 사람이 읽는
# 문구로 그대로 쓰면 부자연스럽다. 필요한 것만 여기서 명시적으로 보정하고,
# 나머지는 언더스코어를 공백으로 바꾸는 기본 규칙을 따른다.
_SPECIES_EN_OVERRIDES = {
    "baby_breath": "baby's breath",
}


def _species_en(species: str) -> str:
    return _SPECIES_EN_OVERRIDES.get(species, species.replace("_", " "))


def load_catalog(catalog_path: Path) -> dict:
    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)
    return {entry["species"]: entry for entry in data["species_list"]}


def validate_species_color(species: str, color: str, catalog_by_species: dict) -> None:
    if species not in catalog_by_species:
        raise ValueError(f"알 수 없는 species: {species!r} (flower_catalog.json에 없음)")
    valid_colors = catalog_by_species[species]["colors"]
    if color not in valid_colors:
        raise ValueError(
            f"{species}는 color={color!r}를 지원하지 않음 (가능한 값: {valid_colors})"
        )


def generate_pick_instruction(species: str, color: str, catalog_by_species: dict) -> str:
    validate_species_color(species, color, catalog_by_species)
    return PICK_INSTRUCTION_TEMPLATE.format(color=color, species_en=_species_en(species))


def instructions_for_recipe(recipe: dict, catalog_by_species: dict) -> list[dict]:
    """
    recipe: ConfirmBar.jsx가 저장하는 실제 스키마
      { "recipe_id", "created_at", "vase_template", "slots": [
          { "slot_id", "tier", "species", "color", "target_slot" }, ... ] }
    반환: 각 슬롯에 대해 {slot_id, species, color, instruction} 리스트
          (place는 target_slot 좌표로 처리하므로 여기 포함 안 함 — 모듈 docstring 참고)
    """
    results = []
    for slot in recipe["slots"]:
        instruction = generate_pick_instruction(slot["species"], slot["color"], catalog_by_species)
        results.append({
            "slot_id": slot["slot_id"],
            "species": slot["species"],
            "color": slot["color"],
            "instruction": instruction,
        })
    return results


def all_species_color_combinations(catalog_by_species: dict) -> list[tuple[str, str]]:
    """데모 수집 범위 산정용: 존재하는 모든 (species, color) 조합 나열.
    decisions/2026-09-24.md #2 기준 조합당 데모 ~50개가 필요하므로,
    len(all_species_color_combinations(...)) * 50 이 SmolVLA 데모 수집의 대략적 총량이다."""
    combos = []
    for species, entry in catalog_by_species.items():
        for color in entry["colors"]:
            combos.append((species, color))
    return combos


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    catalog_by_species = load_catalog(project_root / "DATAS" / "flower_catalog.json")

    print("=== 존재하는 모든 (species, color) 조합과 지시문 ===")
    combos = all_species_color_combinations(catalog_by_species)
    for species, color in combos:
        print(f"  {generate_pick_instruction(species, color, catalog_by_species)!r}")
    print(f"\n조합 수: {len(combos)}개  (조합당 데모 ~50개 가정 시 총 ~{len(combos) * 50}개 필요)")

    print("\n=== 샘플 레시피로 테스트 (실제 recipe 스키마 그대로) ===")
    sample_recipe = {
        "recipe_id": "sample-0001",
        "vase_template": "default_12slot",
        "slots": [
            {"slot_id": "A0", "tier": "focal", "species": "rose", "color": "red",
             "target_slot": {"xyz": [0.055, 0.0, 0.09], "angle_deg": 25}},
            {"slot_id": "B0", "tier": "filler", "species": "baby_breath", "color": "white",
             "target_slot": {"xyz": [0.01414, 0.01414, 0.13], "angle_deg": 10}},
        ],
    }
    for item in instructions_for_recipe(sample_recipe, catalog_by_species):
        print(f"  slot {item['slot_id']}: {item['instruction']!r}")

    print("\n=== 잘못된 조합 검증 (예외가 발생해야 정상) ===")
    try:
        generate_pick_instruction("rose", "blue", catalog_by_species)
        print("  경고: 예외가 발생하지 않음 — validate_species_color 확인 필요")
    except ValueError as e:
        print(f"  예상대로 거부됨: {e}")
