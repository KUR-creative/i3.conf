# i3 워크스페이스 회귀 테스트

## 실행

기존 일회성 이전 도구의 단위 테스트:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

현재 워크스페이스 설정의 실제 키 입력 회귀 테스트:

```bash
python3 tests/workspace_regression.py
```

테스트는 Python 표준 라이브러리와 시스템의 `i3`, `i3-msg`, `Xvfb`, `xmessage`,
`libX11`, `libXtst`를 사용한다. Python 패키지 설치는 필요 없다. Ubuntu에서는
Xvfb가 없으면 `xvfb`, xmessage는 `x11-utils`, XTest 라이브러리는 `libxtst6`
패키지를 준비한다. 테스트가 직접 패키지를 설치하거나 다운로드하지는 않는다.

Xvfb를 PATH에 설치하지 않고 따로 준비했다면 경로를 지정한다:

```bash
python3 tests/workspace_regression.py --xvfb /path/to/Xvfb
```

부분 검사와 다른 설정 사본 검사:

```bash
python3 tests/workspace_regression.py --group single
python3 tests/workspace_regression.py --group pair
python3 tests/workspace_regression.py --group switch
python3 tests/workspace_regression.py --group history
python3 tests/workspace_regression.py --group back
python3 tests/workspace_regression.py --group remember
python3 tests/workspace_regression.py --group layout
python3 tests/workspace_regression.py --config /tmp/workspaces.conf
```

`--timeout`은 각 예상 상태를 기다리는 제한(초)이며 기본값은 4다.
작업 디렉터리와 무관하게 기본 설정 경로는 이 저장소의 workspaces.conf다.

## 검사 내용

메인 숫자는 쌍 전환·쌍별 마지막 포커스 복원·쌍 합류 이동, 키패드는 오른쪽 개별 전환·단일 창 이동이다.
백틱은 메인0의 별칭이며 Shift+백틱도 Shift+메인0과 같다.
기대값은 운영 config에서 추출하지 않고 요구사항에 따라 정한다.

- 숫자/F키 전환 40개 조합: Num Lock 두 상태, 숫자는 쌍 전환·F키는 왼쪽만 전환, 창은 이동하지 않음.
- 키패드 전환 20개 조합: 오른쪽만 전환하고 왼쪽 유지.
- 백틱 전환 2개 조합: F10+0 쌍 전환과 초기 오른쪽 포커스, 같은 키 반복.
- Shift 단일 이동 40개 조합(오른쪽은 키패드, 왼쪽은 F키): 같은/다른 모니터에서 출발, 대상 창만 이동,
  기존 창 보존, 원래 창 포커스, 반대 표시 공간 보존, 사용자 mark 보존 및 내부 mark 정리.
- Shift 쌍 이동 22개 조합(메인 숫자 전체 및 Shift+백틱, Num Lock 두 상태): 양쪽 모든 창 합류, 기존 목적지 창 유지, 원래 창 포커스.
- 이력 기록 40개 조합: 메인 숫자 전환 시 JSON previous·focus 기록, F10/0 대응,
  같은 쌍 재선택 시 보존, 파일 권한 0600. 개별 전환 시 보존, reload 시 보존,
  새 세션 reset, 관리하지 않는 공간에서 실패 시 기록·표시 유지도 검사한다.
- Mod+Tab 왕복 50개 조합: 좌우 출발·모든 쌍·Num Lock 두 상태, F10/0,
  혼합 화면의 정규 쌍 복원, 여러 창 중 마지막 창 복원, 빈 공간 재생성.
  파일 없음·빈 값·잘못된 값·여러 줄·명령 삽입 문자열은 전환하지 않는지도 검사한다.
  동시 previous 6회가 세 왕복으로 처리되는지도 확인한다.
- 숫자키 쌍별 복원 42개 조합: 각 쌍의 좌우 기억, 여러 창 중 마지막 창,
  같은 쌍 재선택의 focus 갱신·previous 보존, Tab과 숫자의 상호 작용,
  기존 F10/0 한 줄 기록의 JSON 전환과 백틱 복원.
- 기존 왕복·기록 검사는 각 사례를 기본 상태로 초기화해 쌍별 기억 검사와 분리한다.
- 레이아웃 보존 8개 사례: 빈/기존 창이 있는 목적지의 splith·tabbed·stacking,
  중첩 구조·내부 percent·창 순서 보존, 사용자 mark·floating·fullscreen·포커스 보존,
  같은 목적지 반복, floating 창만 있는 출발지와 양쪽 모두 빈 출발지.
- Shift 쌍 이동은 JSON 상태 전체를 바꾸지 않는지 확인한다.
- 이동 검사에서는 같은 목적지 반복도 확인한다. 단일 이동에는 floating과
  일반 fullscreen 사례를 포함하고, 포인터를 출발 창 위에 놓은 뒤 상태가 유지되는지도 확인한다.

config의 목적지 값을 테스트에서 추출해 정답으로 사용하지 않는다. 기대하는
이름·좌우 배정·키패드 코드·포커스 정책은 사용자 요구에 따라 독립적으로 검사한다.

## 격리와 한계

- 운영 파일은 읽기만 하고 임시 디렉터리에 테스트 config를 만든다.
- workspace 파일의 출력 이름을 fake-0/fake-1로 바꾸고 보조 프로그램 경로를
  이 저장소의 절대 경로로 지정한다. 상태 파일은 테스트 전용 runtime에만 쓴다. 최소 진입 설정에
  Mod4, 마우스 포커스 추적, 자동 back-and-forth를 설정해 실제 바인딩을 로드한다.
- 기본 base.conf의 앱 실행·bar·기타 단축키까지 검증하는 테스트는 아니다.
- Xvfb의 `-displayfd`로 빈 디스플레이를 할당한다. 실제 DISPLAY·i3 소켓·X 인증
  변수를 상속하지 않으며 IPC 소켓이 테스트 runtime 안인지 확인한다.
- 키 입력은 그 가상 디스플레이에만 보낸다. 종료 시 테스트 프로세스와 임시 파일을 정리한다.
- 실패 시 예상 상태와 실제 테스트 창의 위치·포커스·mark를 출력하고 1로 종료한다.

이것은 실제 모니터의 드라이버·입력 장치·Ptyxis/Chrome의 이벤트 타이밍을 완전히
재현하지 않는다. 이전 단일 IPC 포커스 문제는 가상 환경에서 통과했지만 실제
환경에서 실패했다. 따라서 자동 통과와 실제 사용자 검수·재로그인 검수는 별개다.
빠른 연속 입력에서의 비동기 호출 경합도 실제 세션에서 확인한다.

## 테스트 작성 시 실패 검증

테스트 작성 시 `/tmp`의 설정 사본에 결함을 넣어 검사가 실패하는지 확인했다.
그 변형 코드·실패용 config·뮤테이션 실행기는 저장소에 남기지 않는다.
검사한 결함과 결과는 작업 문서에 기록한다. 앞으로 테스트를 변경할 때도
실패해야 하는 조건을 임시 사본으로 확인한 뒤 정상 설정의 통과를 재확인한다.
