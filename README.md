# 가온교회 파워포인트 슬라이드 자동생성

매주 일요일 가온교회 예배에 사용할 PPT 슬라이드를 Claude Code로 자동 생성하는
프로젝트입니다.

## 사전 준비 (최초 1회)

```bash
# 1. 프로젝트 디렉토리로 이동
cd /Users/yonggyup/Develop/gp1/gaon-church-ppt

# 2. Python 의존성 (lxml만 필요)
pip3 install lxml

# 3. (선택) PDF 미리보기를 원하면 LibreOffice
brew install --cask libreoffice
```

## 매주 사용법

Claude Code 세션을 시작하고 다음 형식으로 입력하시면 됩니다:

```
이번 주 슬라이드 부탁드립니다.

날짜 : 2026-4-19
대표기도 : 임진규 집사
설교제목 : [삶을 낭비하지 말라] 02_그리스도의 아름다움과 기쁨
설교자 : 이봉연 담임목사
성경본문 : 요 17:3, 고후 4:4-6, 빌 3:7-8

요 17:3
영생은 오직 한 분이신 참하나님 아버지와 아버지께서 보내신 예수 그리스도를 아는 것입니다.

고후 4:4-6
4 그들로 말하자면, 이 세상의 신이 믿지 않는 사람들의 마음을 혼미하게 해 하나님의 형상인 그리스도의 영광스러운 복음의 빛이 그들을 비추지 못하게 한 것입니다.
5 우리는 우리 자신을 전파하는 것이 아니라 그리스도 예수께서 주 되신 것과 예수 때문에 우리가 여러분의 종 된 것을 전파합니다.
6 "어둠에서 빛이 비치라"고 명하신 하나님께서 우리의 마음에 예수 그리스도의 얼굴에 있는 하나님의 영광을 아는 빛을 비추셨기 때문입니다.

빌 3:7-8
7 그러나 내게 유익하던 것들을 나는 그리스도 때문에 다 해로운 것으로 여깁니다.
8 내가 참으로 모든 것을 해로 여기는 것은 내 주 그리스도 예수를 아는 지식이 가장 고상하기 때문입니다. ...
```

Claude Code가 `.claude/skills/slide-update/SKILL.md` 의 규칙에 따라
`output/26_04_19.pptx` 를 생성합니다.

## 마스터 템플릿 갱신

새 분기에 찬양곡이나 다른 슬라이드가 바뀌면, 검증된 최신 .pptx로
`templates/master_slides.pptx` 를 직접 교체하세요. Claude Code는 매번 이 파일을
출발점으로 사용합니다.

## 보조 명령어

```bash
# 생성된 파일의 슬라이드 10/11/12 텍스트만 빠르게 확인
python3 scripts/update_slides.py verify output/26_04_19.pptx

# 설교제목 한 줄이 어떻게 분할되는지 미리 테스트
python3 scripts/update_slides.py split-title "복음의 능력"
```

## 디렉토리 구조

```
.
├── CLAUDE.md                         # 프로젝트 컨텍스트 (Claude Code 자동 인식)
├── README.md                         # 본 파일
├── templates/
│   └── master_slides.pptx            # 마스터 (직접 수정 금지, 분기별 교체)
├── output/                           # 생성된 주일 슬라이드 (.gitignore 처리)
├── scripts/
│   └── update_slides.py              # 패킹/언패킹/검증 보조 스크립트
└── .claude/
    └── skills/
        └── slide-update/
            └── SKILL.md              # 슬라이드 변경 상세 규칙
```

## 향후 확장: API화 (선택)

이 프로젝트가 안정화되면, GitHub에 push 후 Claude Code Routines로 등록하여
외부에서 HTTPS POST로 트리거할 수 있습니다 (예: 스마트폰 단축어, n8n 워크플로우).
자세한 절차는 https://code.claude.com/docs/en/routines 참고.
