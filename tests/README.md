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
python3 tests/workspace_regression.py --config /tmp/workspaces.conf
```

`--timeout`은 각 예상 상태를 기다리는 제한(초)이며 기본값은 4다.
작업 디렉터리와 무관하게 기본 설정 경로는 이 저장소의 workspaces.conf다.

## 검사 내용

- 개별 숫자/F키 전환 40개 조합: Num Lock 두 상태, 한쪽만 전환, 창은 이동하지 않음.
- 키패드 쌍 전환 20개 조합: 양쪽 목적지 표시와 오른쪽 고정 포커스.
- Shift 단일 이동 40개 조합: 같은/다른 모니터에서 출발, 대상 창만 이동,
  기존 창 보존, 원래 창 포커스, 반대 표시 공간 보존, 사용자 mark 보존 및 내부 mark 정리.
- Shift 쌍 이동 20개 조합: 양쪽 모든 창 합류, 기존 목적지 창 유지, 원래 창 포커스.
- 이동 검사에서는 같은 목적지 반복도 확인한다. 단일 이동에는 floating과
  일반 fullscreen 사례를 포함하고, 포인터를 출발 창 위에 놓은 뒤 상태가 유지되는지도 확인한다.

config의 목적지 값을 테스트에서 추출해 정답으로 사용하지 않는다. 기대하는
이름·좌우 배정·키패드 코드·포커스 정책은 사용자 요구에 따라 독립적으로 검사한다.

## 격리와 한계

- 운영 파일은 읽기만 하고 임시 디렉터리에 테스트 config를 만든다.
- workspace 파일의 출력 이름만 fake-0/fake-1로 바꾸고, 최소 진입 설정에
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
