---
name: slide-update
description: "Use this skill whenever the user asks to generate the weekly Sunday worship PowerPoint slides for 가온교회 (Gaon Church). Triggers include any mention of 주보, 슬라이드 생성, 주일 예배 PPT, 새 주일, or providing weekly worship info (날짜, 대표기도, 설교제목, 설교자, 성경본문). The skill modifies only slides 10, 11, 12 of the master template and outputs YY_MM_DD.pptx."
---

# 가온교회 주일 슬라이드 자동 변경 SKILL

## 입력 형식

사용자는 매주 다음 형식으로 입력을 제공합니다:

```
날짜 : YYYY-M-D
대표기도 : [이름] [직분]
설교제목 : <한 줄 자유 형식>
설교자 : [이름] [직분]
성경본문 : [본문 표기, 콤마 구분]

[성경 약칭 1] [장:절]
[해당 본문 전문]

[성경 약칭 2] [장:절-절]
[해당 본문 전문]
...
```

## 변경 대상 슬라이드 (반드시 이 3개만)

### Slide 10 — 대표기도자
- 텍스트: `대표기도 : [이름] [직분]`
- 배경 이미지, 위치, 폰트 크기 모두 보존

### Slide 11 — 오늘의 말씀 표지
세 줄 구조 (모두 흰색, 기존 폰트 크기 유지):
1. `오늘의 말씀` (불변)
2. **설교제목 — 사용자가 입력한 한 줄을 그대로 사용** (구조 유추 금지)
3. 성경본문 표기 (예: `요 17:3, 고후 4:4-6, 빌 3:7-8`)

#### 설교제목 처리 규칙 (중요)

기존 마스터 템플릿의 설교제목 영역은 4개의 `<a:r>` run으로 분리되어 있음:
- run1: `[` (en-US)
- run2: `시리즈명` (ko-KR)
- run3: `] NN_` (en-US)
- run4: `부제` (ko-KR)

**사용자 입력은 이 구조를 따르지 않을 수 있음.** 시리즈가 끝나거나 형식이
바뀌면 완전히 다른 제목이 들어옴. 따라서:

1. **기존 4개 run 블록 전체를 통째로 제거**하고, 입력 문자열을 통째로 받음
2. 입력을 **언어 경계로 자동 분할**하여 새 run들로 재구성:
   - 한글 문자 (가-힣, ㄱ-ㅎ, ㅏ-ㅣ) → `lang="ko-KR" altLang="en-US"`
   - 영문/숫자/기호 → `lang="en-US" altLang="ko-KR"`
   - 연속된 같은 언어 문자는 하나의 run으로 묶기
3. 모든 run의 `<a:rPr>`는 다음 유지:
   - `sz="3600"`
   - `dirty="0"`
   - `<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>`
4. 공백 포함 `<a:t>`에는 `xml:space="preserve"` 부여
5. 따옴표는 XML entity 사용: `&#x201C;` `&#x201D;` `&#x2018;` `&#x2019;`

##### 분할 예시

| 사용자 입력 | run 분할 |
|---|---|
| `[삶을 낭비하지 말라] 02_그리스도의 아름다움과 기쁨` | `[`(en) → `삶을 낭비하지 말라`(ko) → `] 02_`(en) → `그리스도의 아름다움과 기쁨`(ko) |
| `복음의 능력` | `복음의 능력`(ko) 단일 run |
| `Identity in Christ — 03_정체성` | `Identity in Christ — 03_`(en) → `정체성`(ko) |

#### 줄바꿈 구조

원본은 `오늘의 말씀` 다음에 `<a:br>` 3개 → 설교제목 → `<a:br>` 2개 → 성경본문 표기.
이 줄바꿈 패턴은 그대로 유지.

### Slide 12 — 성경 본문

각 본문마다:
- 첫 줄: 성경 약칭 + 장:절 (예: `요 17:3`) — bold, 단독 paragraph
- 다음 줄(들): 절 번호로 시작하는 자동 번호 매기기 (`buAutoNum startAt="N"`)
- 본문 사이에는 빈 줄 한 줄 삽입 (`spcPct val="150000"`)
- 본문이 1절짜리면 번호 매기기 없이 줄글로 (paragraph만, no buAutoNum)
- 본문이 여러 절이면 각 절을 별도 paragraph로, 시작 절 번호로 buAutoNum 적용
- 본문 텍스트 스타일: `sz="2400" b="1"`, 색상은
  `<a:schemeClr val="tx2"><a:lumMod val="20000"/><a:lumOff val="80000"/></a:schemeClr>`

## 변경하지 말 것

Slide 1-9, 13-28 (찬양곡, 주기도문, 축도, 광고)은 **절대 손대지 말 것**.

## 작업 절차 (기술 단계)

### 1. 환경 준비

```bash
cd /Users/yonggyup/Develop/gp1/gaon-church-ppt

# 의존성 확인 (최초 1회)
python3 -c "import lxml" 2>/dev/null || pip3 install lxml
```

### 2. 템플릿 압축 해제

`.pptx`는 ZIP 파일임. 작업용 임시 디렉토리에 풀어 슬라이드 XML 직접 수정:

```bash
WORK=$(mktemp -d)
unzip -q templates/master_slides.pptx -d "$WORK"
```

### 3. 슬라이드 XML 수정

`$WORK/ppt/slides/slide10.xml`, `slide11.xml`, `slide12.xml`만 수정.

**XML 파싱은 `lxml.etree` 사용** (네임스페이스 보존).
`xml.etree.ElementTree`는 네임스페이스를 손상시키므로 금지.

#### Slide 10 수정 패턴

`<a:t>허영실</a:t>` 같은 이름 부분과 ` 권사` 같은 직분 부분을 찾아 교체.
공백 보존을 위해 `<a:t xml:space="preserve">` 형태인지 확인.

#### Slide 11 수정 패턴

`<p:txBody>` 내부의 첫 번째 `<a:p>`에서:
1. `오늘의 말씀` 텍스트와 `<a:br>` 3개는 보존
2. 그 뒤의 모든 `<a:r>` (설교제목 부분)을 제거
3. 설교제목 입력을 한글/영문 경계로 분할하여 새 `<a:r>` 시리즈로 삽입
4. 그 뒤의 `<a:br>` 2개 보존
5. 성경본문 표기 영역(이전 `이사야 ... 10:31` 자리) 교체

#### Slide 12 수정 패턴

`<p:txBody>` 내부 모든 `<a:p>`를 제거하고 새 본문 paragraphs로 재구성.
`<a:bodyPr>`와 `<a:lstStyle>`는 보존.

### 4. ZIP 재패킹

```bash
DATE_TAG=$(echo "$INPUT_DATE" | sed 's/^20//;s/-/_/g' | awk -F_ '{printf "%s_%02d_%02d", $1, $2, $3}')
OUTPUT="output/${DATE_TAG}.pptx"

(cd "$WORK" && zip -qr "$OLDPWD/$OUTPUT" .)
rm -rf "$WORK"
```

⚠️ **중요**: `pptx`는 ZIP 내부 파일 순서에 민감함. `[Content_Types].xml`이
ZIP의 첫 번째 엔트리여야 함:

```bash
(cd "$WORK" && zip -qX "$OLDPWD/$OUTPUT" "[Content_Types].xml" && \
  zip -qrX "$OLDPWD/$OUTPUT" . -x "[Content_Types].xml")
```

### 5. 검증

```bash
# 텍스트 추출로 변경 확인
python3 scripts/update_slides.py verify "$OUTPUT"

# (선택) PDF 변환하여 시각 확인 — LibreOffice 필요
soffice --headless --convert-to pdf "$OUTPUT" --outdir /tmp/
open /tmp/${DATE_TAG}.pdf
```

## 출력 파일명

`output/YY_MM_DD.pptx` (예: 2026-4-19 → `output/26_04_19.pptx`)

## 응답 톤

박용규 집사님은 시간이 빠듯하므로 다음 형식으로 간결하게 보고:

```
✅ output/26_04_19.pptx 생성 완료

변경 사항:
• Slide 10: 대표기도 → 임진규 집사
• Slide 11: 02_그리스도의 아름다움과 기쁨 / 요 17:3, 고후 4:4-6, 빌 3:7-8
• Slide 12: 본문 3개 (요 17:3 1절, 고후 4:4-6 3절, 빌 3:7-8 2절)
```

불필요한 설명, 의도 재확인, 추가 제안 등은 생략.

## 자주 마주치는 함정

1. **언어 분할 시 공백 처리**: `]` 다음 공백은 영문 run에 포함 (`] 02_`)
2. **숫자만 있는 토큰**: `02`, `17:3` 같은 숫자/기호는 영문 run으로 처리
3. **하이픈/언더스코어 처리**: `02_그리스도` 같은 경우 `02_`(en)와 `그리스도`(ko)로 분리
4. **bodyPr 자동맞춤**: Slide 11의 `<a:bodyPr><a:normAutofit/></a:bodyPr>` 보존
5. **번호 매기기 색상**: Slide 12에서 `buAutoNum`은 paragraph의 `<a:pPr>`에
   설정되며, 색상은 paragraph 내 첫 run의 색상을 따름
