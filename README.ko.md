<p align="center"><img src="assets/banner.png" alt="Agent Run Report — 내 PC에서 만드는 AI 코딩 에이전트 활동 보고서" width="100%"></p>

<p align="center">
  <a href="https://github.com/kks0488/agent-run-report/actions/workflows/ci.yml"><img src="https://github.com/kks0488/agent-run-report/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT 라이선스"></a>
  <img src="https://img.shields.io/badge/runtime_dependencies-0-brightgreen.svg" alt="실행 시 외부 패키지 불필요">
  <img src="https://img.shields.io/badge/Python-%3E%3D3.9-3776AB.svg" alt="Python 3.9 이상">
</p>

<p align="center"><strong>한국어</strong> · <a href="README.md">English</a></p>

<h2 align="center">AI 코딩 에이전트가 실제로 무엇을 했는지 확인하세요.</h2>

<p align="center">Claude Code와 OpenAI Codex CLI를 쓰면서 세션, 도구 사용, 실패, 토큰 사용량을 살펴보고 싶은 개발자를 위한 도구입니다. 내 PC의 로그를 오프라인 HTML 파일 하나로 정리하며, 실행에 별도 패키지가 필요하지 않습니다.</p>

<p align="center"><img src="assets/screenshot.png" alt="날짜별 활동, 도구 사용량, 프로젝트와 세션을 보여 주는 Agent Run Report" width="100%"></p>

<table>
  <tr>
    <td width="50%"><strong>두 에이전트를 한 보고서에</strong><br>Claude Code와 OpenAI Codex CLI의 JSONL 로그를 읽습니다. 날짜, 에이전트, 프로젝트로 범위를 좁힐 수 있습니다.</td>
    <td width="50%"><strong>활동을 한눈에</strong><br>날짜별 세션, 활동 시간, 토큰, 도구 호출과 실패, 프로젝트별 합계를 보여 줍니다.</td>
  </tr>
  <tr>
    <td><strong>인터넷 없이 살펴보기</strong><br>세션 검색·정렬과 상세 보기를 지원하고, 시스템 설정에 따라 밝은 화면과 어두운 화면으로 바뀝니다. 화면에 필요한 요소는 모두 파일 안에 들어 있습니다.</td>
    <td><strong>민감한 내용은 기본으로 제외</strong><br>외부로 업로드하지 않습니다. 프롬프트와 도구 입출력은 내보내지 않으며, 제목과 파일 경로는 직접 옵션을 켜야 포함됩니다.</td>
  </tr>
</table>

## 빠르게 시작하기

Python 3.9 이상이 필요합니다. [pipx](https://pipx.pypa.io/)로 설치하려면:

```sh
pipx install git+https://github.com/kks0488/agent-run-report
agent-run-report --demo --out demo-report.html
```

또는 사용 중인 Python 환경에 pip로 설치하세요.

```sh
pip install git+https://github.com/kks0488/agent-run-report
python3 -m agent_run_report --demo --out demo-report.html
```

저장소를 내려받으면 패키지 설치 없이 바로 실행할 수도 있습니다.

```sh
git clone https://github.com/kks0488/agent-run-report.git
cd agent-run-report
python3 -m agent_run_report --demo --out demo-report.html
```

생성된 `demo-report.html`을 열어 보세요. 에이전트 로그가 없어도 사용할 수 있습니다. 데모에는 **고정된 14일(2026-09-28~2026-10-11) 동안의 가상 세션 24개**가 들어 있습니다. 두 에이전트와 가상 프로젝트 5개, 쉬는 날과 바쁜 날, 일부 서브에이전트 활동을 담았습니다. 개인 로그는 읽지 않으며, 실행 날짜가 바뀌어도 데모 기간은 같습니다.

내 로그로 보고서를 만들려면:

```sh
python3 -m agent_run_report --since 7d --out report.html
python3 -m agent_run_report --source codex --project sample-api --since 2026-10-01 --until 2026-10-11 --out codex-report.html
python3 -m agent_run_report --since 30d --out report.html --json report.json
```

## 사용법과 옵션

설치 후 쓰는 `agent-run-report`와 `python3 -m agent_run_report`는 같은 옵션을 받습니다.

| 옵션 | 동작 / 기본값 |
| --- | --- |
| `-h`, `--help` | 도움말을 보여 주고 종료합니다. |
| `--since 7d\|30d\|YYYY-MM-DD` | 최근 며칠 또는 UTC 기준 시작 날짜를 지정합니다. 기본값: 최근 30일. `--demo`에서는 데모 전체 기간. |
| `--until YYYY-MM-DD` | UTC 기준 해당 날짜까지 포함합니다. 기본값: 종료일 제한 없음. |
| `--source all\|claude\|codex` | 에이전트를 선택합니다. 기본값: `all`. |
| `--project SUBSTR` | 프로젝트의 전체 작업 폴더 경로에서 대소문자 구분 없이 문자열을 찾습니다. |
| `--out PATH` | HTML 저장 경로. 기본값: `agent-run-report.html`. |
| `--json PATH` | 같은 개인정보 설정을 적용한 집계 JSON도 저장합니다. `--out`과 다른 경로를 쓰세요. |
| `--claude-dir PATH` | Claude Code 로그 폴더 또는 JSONL 파일 하나. 기본값: `~/.claude/projects`. |
| `--codex-dir PATH` | Codex CLI 로그 폴더 또는 JSONL 파일 하나. 기본값: `~/.codex/sessions`. |
| `--include-titles` | 기록된 Claude 세션 제목을 포함합니다. 기본은 숨김이며, 제목에 개인적인 내용이 들어 있을 수 있습니다. |
| `--full-paths` | 프로젝트와 수정 파일의 경로를 포함합니다. 현재 사용자의 홈 폴더 부분은 `~`로 바꿉니다. |
| `--open` | 저장한 HTML을 기본 브라우저로 엽니다. 기본은 꺼짐. |
| `--demo` | 함께 제공되는 가상 로그만 읽습니다. 개인 로그 폴더 옵션은 사용하지 않습니다. |
| `--version` | 설치된 버전을 보여 주고 종료합니다. |

저장할 폴더는 미리 만들어 주세요. CLI는 파일만 만들며 상위 폴더는 만들지 않습니다. 조건에 맞는 세션이 없으면 안내를 출력하고 종료 코드 `1`을 반환합니다.

## 동작 방식과 지표 기준

JSONL 로그를 한 줄씩 읽고, 지표를 집계한 뒤 개인정보 설정을 적용해 HTML 파일 하나로 만듭니다. Claude 로그는 `~/.claude/projects` 아래의 `*.jsonl`, Codex 로그는 `~/.codex/sessions` 아래의 `rollout-*.jsonl`을 하위 폴더까지 찾습니다. 경로 옵션에 파일 하나를 지정할 수도 있습니다. 날짜 검색에서는 파일 수정 시각으로 먼저 후보를 줄이고, 실제 포함 여부는 이벤트의 기록 시각으로 판단합니다.

두 로그 형식은 **공식적으로 문서화되어 있지 않아 바뀔 수 있습니다**. 파서는 잘못된 줄을 건너뛰고, 모르는 기록 유형과 필드를 무시하며, 값이 빠진 경우에도 가능한 범위에서 읽습니다. 인식한 기록만 집계하므로 로그가 누락되거나 형식이 달라지면 수치가 적게 잡힐 수 있습니다.

| 지표 | 계산 기준 |
| --- | --- |
| 세션 | 선택한 기간에 인식 가능한 이벤트가 있는 `(에이전트, 세션 ID)` 조합의 수입니다. 여러 날에 걸친 세션은 활동이 기록된 각 날짜에 나타나므로 날짜별 세션 수의 합과 전체 세션 수는 다를 수 있습니다. |
| 활동 시간 | 세션별로 중복 시각을 제거하고 시간순으로 정렬한 뒤, 연속 이벤트 사이의 `min(시간 차이, 300초)`를 더합니다. 동시에 진행한 세션도 각각 합산합니다. 사람의 근무 시간이 아닌, 로그에서 추정한 에이전트 활동 시간입니다. 이벤트가 하나면 0초입니다. |
| 도구 호출 | Claude의 `tool_use`와 Codex의 함수·커스텀 도구 호출을 셉니다. 같은 로그 안에서는 호출 ID가 있으면 중복을 제거합니다. |
| 실패 | 도구 결과의 명시적인 `is_error: true`, 실패·오류 상태 필드, 0이 아닌 종료 코드, 인식 가능한 셸 종료 문구를 셉니다. Codex 오류 이벤트도 포함하며, 도구를 특정할 수 없는 오류도 집계합니다. 같은 로그 안에서 같은 호출 ID의 실패는 한 번만 셉니다. 단순히 “error”라는 단어가 있다는 이유로 실패로 세지는 않습니다. |
| 실패율 | 기록된 실패 수 ÷ 도구 호출 수입니다. 호출이 없으면 0입니다. 도구 미상 오류도 포함하므로 개별 호출이 실패할 확률과 정확히 같지는 않습니다. |
| 토큰 | 캐시를 제외한 입력 + 출력 + 캐시 읽기 + 캐시 쓰기입니다. Claude는 메시지 ID별 사용량의 증가분만 더해 중복을 제거합니다. Codex는 누적 사용량의 이전 최댓값을 넘는 증가분만 더하고, 누적값이 없으면 마지막 사용량을 씁니다. Codex 입력에 포함된 캐시 읽기는 입력에서 뺀 뒤 별도로 셉니다. |
| 수정 파일 | 편집·쓰기·노트북 작업과 패치 헤더에서 찾은 서로 다른 파일 경로 수입니다. 읽은 파일 전체나 셸에서 바꾼 모든 파일을 뜻하지는 않습니다. 파일 이름은 기본으로 숨깁니다. |
| 서브에이전트 활동 | Claude의 sidechain 기록, Codex에서 서브에이전트로 표시된 기록과 인식 가능한 spawn/Task/Agent 호출을 셉니다. 활동 흔적의 수이며, 서로 다른 서브에이전트의 수가 아닙니다. |

날짜와 날짜별 집계는 모두 **UTC 기준**입니다. 첫 기록과 마지막 기록 사이에 활동이 없는 날도 0으로 표시합니다. 토큰 차트는 캐시 읽기·쓰기를 합쳐 보여 주고, 세션 상세와 JSON에서는 구분합니다. **달러 비용 추정은 의도적으로 제공하지 않습니다.** 가격은 바뀌며, 기록된 토큰 수만으로 실제 청구액을 알 수 없기 때문입니다.

## 개인정보

보고서 생성은 내 PC의 로그를 읽고 파일을 저장하는 작업입니다. 네트워크 요청을 보내지 않으며, 결과 HTML에는 SVG 차트, 스타일, 스크립트가 모두 들어 있어 외부 파일을 불러오지 않습니다. 패키지 설치와 이 README의 배지 표시는 별도로 인터넷을 사용합니다.

기본 설정에서는 HTML과 JSON 모두 프롬프트, 응답 본문, 도구 입출력, 세션 제목, 프로젝트 전체 경로, 수정 파일 이름을 제외합니다. 프로젝트 폴더 이름, 짧게 줄인 세션 ID, 모델, 기록 시각, 집계 수치는 남습니다. `--include-titles`와 `--full-paths`를 켜면 해당 항목을 추가합니다. 홈 경로를 `~`로 바꾸는 것만으로 완전히 익명화되지는 않으므로, 공유 전에 내용을 확인하세요.

## 다크 모드

시스템의 화면 모드 설정을 자동으로 따릅니다.

<p align="center"><img src="assets/screenshot-dark.png" alt="다크 모드로 표시한 Agent Run Report" width="75%"></p>

## 프로젝트 구성

```text
agent-run-report/
├── agent_run_report/
│   ├── __init__.py       # 버전
│   ├── __main__.py       # python -m 실행 진입점
│   ├── cli.py            # 옵션과 파일 저장
│   ├── parsers.py        # Claude / Codex 로그 읽기
│   ├── metrics.py        # 집계와 개인정보 처리
│   ├── render.py         # HTML, SVG, CSS, JavaScript
│   └── demo/
│       ├── claude/       # 가상 JSONL 세션
│       └── codex/        # 가상 JSONL 기록
├── tests/test_report.py
├── .github/workflows/ci.yml
├── pyproject.toml
├── README.md
├── README.ko.md
└── LICENSE
```

## 테스트 실행

저장소 최상위 폴더에서 실행합니다. 테스트용 패키지는 필요하지 않습니다.

```sh
python -m unittest discover -s tests
python -m agent_run_report --demo --out /tmp/r.html
```

CI는 push와 pull request마다 Ubuntu에서 Python **3.9, 3.11, 3.13**으로 두 명령을 실행합니다. 테스트는 로그 읽기, 중복 제거, 날짜 필터, 활동 시간, 개인정보 처리, HTML 생성, CLI 동작, 데모의 활동 분포를 확인합니다.

## 앞으로 할 일 — 아직 구현되지 않았습니다

- 가상 예제와 회귀 테스트로 검증하는 로그 형식 추가 지원.
- 두 기간의 활동을 직접 비교하는 기능.

## 자주 묻는 질문

**API 키나 실행 중인 에이전트가 필요한가요?** 아니요. 저장된 로그만 있으면 됩니다. `--demo`는 로그도 필요 없습니다.

**세션을 찾지 못한다고 나와요.** 로그 경로를 확인하고 `--since` 범위를 넓히거나 `--project` 조건을 빼 보세요. 기본 범위는 최근 30일이며, 인식 가능한 JSONL 기록만 셉니다. 로그를 다른 곳에 저장했다면 경로 옵션을 지정하세요.

**서비스 대시보드와 합계가 달라요.** 이 도구는 요금 명세가 아닌, 내 PC에서 인식한 사용량 기록을 보여 줍니다. 로그 누락, 형식 변경, 검색 범위, 캐시 집계 방식에 따라 달라질 수 있습니다. 금액은 추정하지 않습니다.

**HTML을 다른 사람에게 보내도 되나요?** 파일 하나로 열 수 있고 인터넷도 필요 없습니다. 기본 설정에서도 프로젝트 폴더 이름, 모델, 시각, 집계 수치는 보입니다. 공유 전에 확인하고, 제목·경로 포함 옵션을 썼다면 더 주의해서 살펴보세요.

## 기여하기

이슈와 PR을 환영합니다. 파서를 수정할 때는 작은 **가상 로그**나 테스트 사례에 예상 지표를 함께 적어 주세요. 개인 로그나 비밀 정보는 첨부하지 마세요. 위의 테스트와 데모 명령을 실행하고, 두 README를 실제 동작에 맞게 함께 수정해 주세요.

## 라이선스

[MIT](LICENSE) © 2026 Kyoungsoo Kim.
