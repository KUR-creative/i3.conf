# 개인 앱 실행 단축키 분리

## 현재 기능 목록

`Mod`는 Super 키다. `→` 뒤의 키는 앞의 키를 뗀 다음 누른다.

| 단축키 | 동작 |
|---|---|
| Mod+Enter → Enter | 새 터미널 창 |
| Mod+Enter → c | 새 터미널에서 `codex --not-so-yolo` 실행. 종료 후 같은 창·디렉터리에 Bash가 남음 |
| Mod+Enter → b | 새 Chrome Stable 창 |
| Mod+Enter → BackSpace | 표시 중인 최신 생성·갱신 알림의 기본 액션 실행. 기본 액션이 없으면 액션 선택 메뉴 |
| Mod+Enter → Escape | 실행 모드 취소 |
| Mod+BackSpace | 표시 중인 알림 하나 닫기. 액션 실행 안 함 |

앱 실행과 알림 액션 요청 후 기본 모드로 돌아온다. 기본 모드의 Mod+b는 사용하지 않는다.
알림 대상과 검수 절차는 [알림 단축키 문서](notification-shortcut.md)를 참고한다.

## 변경

- 개인 앱 실행 단축키를 `config.d/shortcuts.conf`에 모으고 메인 `config`에서 명시적으로 include한다.
- 기존 터미널 실행 정의를 base.conf에서 옮기고, Mod+Enter를 앱 실행 모드 진입 키로 사용한다.
- Mod+Enter를 누르고 키를 뗀 다음 Enter는 새 터미널, c는 새 Ptyxis 창에서 `~/.local/bin/codex --not-so-yolo`를 실행한다.
- Codex는 `bash -c` 안에서 실행하고, 종료 후 `exec bash -i`로 같은 창과 작업 디렉터리에 대화형 셸을 남긴다. Codex가 오류로 종료해도 셸을 실행한다.
- 같은 모드에서 b는 새 Chrome Stable 창을 연다. 중복 터미널 키 t는 제거했다. 실행 후 기본 모드로 돌아온다.
- Escape는 실행하지 않고 기본 모드로 돌아온다. 기존 기본 모드의 Mod+b는 제거한다.
- 알림 하나 닫기 정의를 base.conf에서 shortcuts.conf로 옮기고, 실행 모드의 BackSpace에 `dunstctl action 0`을 연결한다.
- 실행 모드 이름에 키 안내를 넣어 i3bar에 표시한다.

## 검증

- `i3 -C -c ~/.config/i3/config`: 통과. 샌드박스의 런타임 로그 경로 제한 때문에 임시 XDG_RUNTIME_DIR을 사용했다.
- Mod+Return은 모드 진입으로 한 번 정의되어 있으며, 기본 모드에 Mod+b는 없다.
- 설치된 Ptyxis 매뉴얼에서 `-- PROGRAM ARGUMENTS` 실행 형식을 확인했다.
- `codex --not-so-yolo --help`: 종료 코드 0으로 옵션 인식 확인.
- `git diff --check`: 통과.
- Codex 대체 명령의 정상 종료·오류 종료 모두에서 후속 `bash -i` 실행과 작업 디렉터리 유지를 확인했다.
- 실제 키 입력은 사용자 검수 대기.

## 적용과 검수

1. Mod+Shift+c로 설정을 리로드한다.
2. Mod+Enter를 누르고 키를 떼면 bar에 앱 실행 안내가 표시되는지 확인한다.
3. c로 새 터미널에서 Codex가 실행되는지 확인하고, Codex 종료 후 같은 창에 Bash 프롬프트가 남는지 확인한다.
4. 다시 Mod+Enter → Enter로 새 터미널, Mod+Enter → b로 새 크롬 창이 열리는지 확인한다.
5. 각 실행 후 기본 모드로 돌아오는지, Mod+Enter → Escape는 창을 열지 않고 취소하는지 확인한다.
6. Mod+v → Mod+Enter → Enter는 위아래, Mod+g → Mod+Enter → b는 좌우로 배치되는지 확인한다.
7. 기본 모드의 Mod+b는 크롬을 실행하지 않는지 확인한다.

## 되돌리기

이 변경 커밋을 `git revert`한 뒤 설정을 리로드한다. 이미 열린 창은 그대로 남는다.
