# 가온교회 파워포인트 슬라이드 자동생성 프로젝트

## 프로젝트 목적

매주 일요일 가온교회(담임: 이봉연 목사) 예배에 사용할 파워포인트 슬라이드를
직전 주의 마스터 템플릿으로부터 자동 생성합니다.

박용규 안수집사가 매주 예배 정보(대표기도자, 설교제목, 설교자, 성경본문)를
입력하면, Claude Code가 `templates/master_slides.pptx`를 기반으로 슬라이드
**10번(대표기도), 11번(오늘의 말씀), 12번(성경 본문)** 만 변경하여
`output/YY_MM_DD.pptx`로 저장합니다.

## 작업 시 반드시 따라야 할 규칙

상세 변경 규칙은 `.claude/skills/slide-update/SKILL.md`에 정의되어 있습니다.
매 작업 시 이 SKILL을 먼저 읽고 그 절차를 정확히 따르세요.

## 프로젝트 구조

```
gaon-church-ppt/
├── CLAUDE.md                          # 본 파일
├── README.md                          # 사람용 문서
├── templates/
│   └── master_slides.pptx             # 마스터 템플릿 (절대 직접 수정 금지)
├── output/                            # 생성된 주일 슬라이드 (YY_MM_DD.pptx)
├── scripts/
│   └── update_slides.py               # 보조 스크립트 (선택적 사용)
└── .claude/
    └── skills/
        └── slide-update/
            └── SKILL.md               # 슬라이드 변경 규칙 (핵심)
```

## 마스터 템플릿 갱신 정책

- 새 분기마다 찬양곡이 바뀌어 슬라이드 1-9, 13-28이 갱신될 때, 박용규 집사가
  검증된 최신 .pptx를 `templates/master_slides.pptx`로 수동 교체합니다.
- 매주 작업으로 생성된 `output/YY_MM_DD.pptx`는 마스터로 자동 승격되지 않습니다.

## 사용자 정보

- 박용규(Yongkyu Park) 안수집사
- 가온교회(서울 소재 소형 교회)
- 주중 직장 업무가 바쁘므로 주말에 빠르게 처리할 수 있어야 함

## 작업 톤

작업 보고는 간결하게: 변경된 3개 슬라이드 요약 + 출력 파일 경로만 제시.
불필요한 부가 설명 생략.
