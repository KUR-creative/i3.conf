# ws CLI와 로컬 설치

## 설치 상태

이 머신에는 다음 심볼릭 링크를 설치했다.

```text
~/.local/bin/ws -> ~/.config/i3/scripts/workspace-pair.py
```

원본 프로그램에 실행 권한을 부여했다. 현재 PATH에 `~/.local/bin`이 이미
포함되어 있어 셸 설정을 추가로 바꾸지 않았다. 링크는 저장소 밖의 로컬 설치
항목이며 Git에는 원본 코드·실행 권한·설치 안내를 기록한다.

별도 설치 스크립트는 만들지 않았다. 링크 하나를 설치하는 단계라 아래 명령으로
충분하다. 다른 머신에 저장소를 같은 위치로 가져왔다면 다음처럼 설치한다.

```bash
mkdir -p "$HOME/.local/bin"
chmod u+x "$HOME/.config/i3/scripts/workspace-pair.py"
ln -s "$HOME/.config/i3/scripts/workspace-pair.py" "$HOME/.local/bin/ws"
ws --help
```

이미 설치된 링크는 다시 만들 필요가 없다. `ln -s`는 기존 파일을 덮어쓰지 않는다.
`command -v ws`와 `readlink "$HOME/.local/bin/ws"`로 명령과 링크를 확인한다.
다른 머신에서 PATH에 해당 디렉터리가 없으면 그 머신의 로그인 환경에 추가하거나
아래 절대 경로를 사용한다.

## 사용법

```text
usage: ws [-h] [--move] TARGET
```

| 명령 | 동작 |
|---|---|
| `ws 1` ~ `ws 9` | 해당 정규 쌍을 표시하고 그 쌍의 마지막 포커스 쪽·창 복원 |
| `ws 0` | 열 번째 쌍인 F10+0 표시·포커스 복원 |
| `ws previous` | 이전 정규 쌍 복원. 반복하면 왕복 |
| `ws 3 --move` | 양쪽 레이아웃 묶음을 쌍 3에 합류시키고 원래 창 따라가기. 이력은 갱신하지 않음 |
| `ws reset` | 세션의 previous·쌍별 포커스 기록 초기화 |
| `ws -h` 또는 `ws --help` | 사용법·옵션·예시·상태 위치 출력. i3 연결이나 상태 변경 없음 |

`--move`는 숫자 목적지에만 사용할 수 있다. 대상 생략·잘못된 대상·잘못된 옵션은
usage와 오류를 출력하고 종료 코드 2로 끝난다. 실행 중 i3 연결·전환 오류는 1,
성공과 도움말은 0이다. 코드·의존성은 기존 프로그램 그대로이며 Python 표준
라이브러리와 i3-msg만 사용한다.

## i3와 외부 앱의 공통 진입점

`config.d/workspaces.conf`의 쌍 전환·이전 쌍 복원·쌍 이동·새 세션 초기화는
모두 `~/.local/bin/ws`를 호출한다. PATH가 다른 GUI 앱에도 같은 명령을 제공한다.
i3는 exec에서 홈 경로를 확장하지만 일반 앱의 인자 배열은 `~`를 자동 확장하지
않을 수 있으므로 외부 앱에는 다음 실제 절대 경로를 사용하면 된다.

```text
/home/kur/.local/bin/ws
```

예를 들어 Python 앱에서는:

```python
subprocess.run(['/home/kur/.local/bin/ws', '3'], check=True)
```

해당 i3 세션 사용자로 실행하고 i3-msg가 그 세션에 연결할 수 있는 환경을 사용한다.
터미널에서는 PATH로 찾은 `ws`를 바로 호출해도 된다. 새로운 서비스나 상주 프로세스는 없다.
`i3-msg 'workspace ...'`를 직접 실행하면 이 프로그램을 거치지 않으므로 이력은
즉시 갱신되지 않는다. 기록·쌍별 포커스를 사용하는 외부 앱은 ws를 공통 진입점으로 쓴다.

## 상태와 관련 문서

상태 경로는 이전과 같은 `$XDG_RUNTIME_DIR/i3-workspace-pair`이며 JSON의 previous와
쌍별 focus 10개를 저장한다. 이번 CLI 설치로 기존 상태를 초기화하거나 이전하지 않는다.

- [상태 구조·갱신 정책](previous-workspace-pair.md)
- [레이아웃 묶음 이동](move-layout-preservation.md)
- [기능 체크리스트](workspace-review-checklist.md)
- [자동 검사 실행](../tests/README.md)

## 검수

- 링크·PATH 및 -h/--help, 잘못된 인자의 종료 코드, 설정 문법을 검사한다.
- 가상 i3에서 기존 키 전환·레이아웃·포커스·상태 회귀를 실행한다.
- 실제 사용자는 `ws --help`를 확인하고 필요할 때 `i3-msg reload`로 공통 경로를 적용한다.
  실제 공간 전환·창 이동 검사는 사용자 작업을 피해서 직접 수행한다.


검사 결과:

- 실제 설치 링크를 통해 -h/--help 정상 종료와 예시 출력을 확인했다.
- 대상 생략·잘못된 대상·잘못된 옵션·previous --move는 종료 코드 2로 끝났고,
  i3 연결이 불가능한 임시 환경에서도 도움말·인자 오류는 상태 파일을 만들지 않았다.
- 새 직접 실행 경로로 기존 가상 i3 회귀 264개 조합 통과.
- 기존 단위 테스트 6개, i3 설정 문법·diff 검사 통과.
- 실제 사용자 세션의 전환·창 이동·리로드는 자동으로 실행하지 않았다.
