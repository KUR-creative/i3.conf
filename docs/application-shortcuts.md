# 개인 앱 실행 단축키 분리

## 현재 기능 목록

`Mod`는 Super 키다. `→` 뒤의 키는 앞의 키를 뗀 다음 누른다.

| 단축키 | 동작 |
|---|---|
| Mod+Enter → Enter | Ptyxis에서는 같은 디렉터리로 내부 새 창 요청. 다른 앱·빈 공간에서는 일반 새 터미널 |
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

### Ptyxis 헤더바와 세션 복원 (2026-11-15)

- Enter 실행 줄에 `G_RESOURCE_OVERLAYS`를 지정해 `~/.config/ptyxis-no-header/ptyxis-window.ui`를 사용한다. 원본 실행 파일은 수정하지 않는다.
- UI 복사본의 `AdwHeaderBar` (`header_bar`)에 `visible=false`를 추가했다. 사용자가 헤더바 제거 동작을 확인했다.
- 참고·UI 재생성 스크립트는 `/home/kur/dev/env.kur-big/essential/ptyxis-no-header.sh`다. i3는 이 스크립트를 호출하지 않는다. Ptyxis 업데이트 후 필요하면 다시 실행한다.
- 이 헤더바·세션 복원 단계에서는 `.bashrc`를 수정하지 않았다. 이미 실행 중인 Ptyxis는 처음 실행된 환경을 유지하므로, 새 실행 줄의 환경변수가 기존 프로세스로 전달되지는 않는다.
- 조사 시 Ptyxis 프로세스 하나, 창 13개, `restore-session=true`를 확인했다. 저장된 창의 복원은 중복 창 발생의 유력한 원인이다. 당시 최초 실행 과정은 재현하지 않았다.
- Ptyxis 소스는 일반 프로세스 최초 명령 처리 시 세션을 복원하고, `--standalone`에서는 그 복원을 건너뛴다. `--standalone` 자체가 세션 복원의 원인이라는 이전 설명은 잘못됐다.
- `restore-session=false`를 실제 GSettings에 적용했다. i3 일반 시작 시에도 같은 값을 설정하도록 `exec`를 추가했다. `reload`는 일반 `exec`를 다시 실행하지 않는다.
- 실행 방식은 공유 프로세스에 `--new-window`를 요청한다. 세션 복원을 꺼서 다음 프로세스 시작 때 저장된 창을 다시 열지 않도록 한다. 기존 창과 작업은 종료하지 않는다.
- 검증: 실행 줄과 같은 환경·명령에 고유 테스트 제목만 추가해 창 수가 13→14로 정확히 하나 증가함을 확인했다. 테스트 창만 종료했다. 설정 문법, 셸 문법, `git diff --check` 통과.
- 남은 사용자 검수: Mod+Enter → Enter로 창 하나가 열리는지 확인. 이후 자연스럽게 모든 Ptyxis 작업을 마치고 다시 실행했을 때 과거 창들이 복원되지 않는지 확인. 첫 실행 복원 동작은 자동 검증에서 기존 작업을 종료해 재현하지 않았다.
- 되돌릴 때 Enter 실행 줄에서 환경변수를 제거하고, 세션 복원도 원하면 `gsettings set org.gnome.Ptyxis restore-session true`로 되돌린다. i3의 해당 `exec`도 제거한다. 사용자 설정 리로드 후 향후 실행에 적용한다.
- 소스 참고: https://gitlab.gnome.org/chergert/ptyxis/-/blob/main/src/ptyxis-application.c

### 포커스한 Ptyxis의 디렉터리 계승

- 사용자 실험에서 `.bashrc`의 `PROMPT_COMMAND=promptFn`이 VTE 경로 알림을 덮어쓰는 문제가 확인됐다.
  원본은 `/tmp/bashrc-before-vte-cwd-20261115-191423-bmelovus.bak`에 백업했다.
  promptFn과 __vte_osc7을 함께 실행하도록 변경했고 사용자가 Ctrl+Shift+N으로 같은 디렉터리의 새 창을 확인했다.
- 이 전제 위에서 Mod+Enter → Enter를 앱에 따라 분기한다. `xdotool getactivewindow`와
  `xprop WM_CLASS`로 현재 X11 창을 확인한다. 실제 Ptyxis 클래스는 소문자 `ptyxis`다.
- Ptyxis라면 `xdotool key --clearmodifiers ctrl+shift+n`으로 그 창의 내부 새 창 기능을 요청한다.
  GUI PID의 cwd를 추측하거나 모든 셸의 프로세스를 탐색하지 않는다.
- 다른 앱이나 빈 워크스페이스라면 기존 `ptyxis --new-window`를 사용하고 헤더바 제거용
  G_RESOURCE_OVERLAYS 환경을 유지한다. 세션 복원은 계속 꺼둔다.
- config의 작은 셸 if로 분기해 별도 실행 프로그램을 추가하지 않았다. 사용자 설치한
  xdotool과 기존 xprop/grep을 사용한다. 일반 기능은 검증된 도구를 우선한다.
- 진입 Mod+Enter와 모드 안 Enter를 모두 `--release`로 처리한다. 진입을 keypress에
  처리하면 그 Enter의 release가 새 모드의 Enter에도 걸려 선택을 건너뛸 수 있다.
  기본 모드로 먼저 돌아온 뒤 키를 전달해 i3 실행 모드에 다시 잡히지 않게 한다.
- if 전체를 i3 exec의 큰따옴표 안에 두고 내부 큰따옴표를 피했다. i3의 설정 파싱과
  실행 명령 파싱을 모두 통과해야 하므로 실제 키 입력 검사로 셸 실행까지 확인했다.
  grep의 `, .ptyxis.$`는 xprop이 출력하는 마지막 클래스 문자열 `, "ptyxis"`에 대응한다.
- 새 창·경로 계승은 VTE 후크가 적용된 기존 터미널에서 검수한다. 기존 창에서는
  필요하면 `source ~/.bashrc`로 먼저 적용한다. 일반 i3 exec에 `$PWD`를 붙이는 방식은 사용하지 않는다.
- c/Codex·b/브라우저·알림 액션·Escape 정의는 그대로 유지한다.

자동 검증:

- `tests/application_shortcuts_regression.py`에서 격리한 Xvfb/i3에 실제 xdotool 키를 보낸다.
- xev의 클래스를 ptyxis로 설정해 Ctrl+Shift+N 수신을 확인한다. 일반 실행이 함께 호출되지 않는지도 검사한다.
- 다른 앱·빈 공간은 가짜 ptyxis 실행을 정확히 한 번 기록하고 헤더바 환경도 유지한다. Escape는 아무 앱도 실행하지 않는다.
- 실제 사용자 창에 키를 보내거나 새 창을 자동으로 열지는 않는다. 실제 디렉터리 계승은 사용자 검수 대상이다.
- 위 분기·키 전달·빈 공간·취소 검사는 모두 통과했다. 이전 설정의 임시 사본은
  Ctrl+Shift+N을 보내지 않고 일반 실행을 호출해 새 검사에서 실패했다(exit 1).
- i3 설정 문법·셸 문법·diff 및 기존 단위 테스트 6개도 통과했다.

추가 사용자 검수:

1. `i3-msg reload`로 적용한다.
2. Ctrl+Shift+N이 정상인 Ptyxis에서 홈이 아닌 디렉터리로 이동한다.
3. Mod+Enter를 누르고 키를 뗀 뒤 Enter를 눌러 창이 하나만 열리고 `pwd`가 같은지 확인한다.
4. 브라우저 등 다른 앱과 빈 워크스페이스에서도 새 터미널이 하나 열리는지 확인한다.
5. Escape 취소, c/Codex, b/브라우저와 알림 단축키도 확인한다.

1. Mod+Shift+c로 설정을 리로드한다.
2. Mod+Enter를 누르고 키를 떼면 bar에 앱 실행 안내가 표시되는지 확인한다.
3. c로 새 터미널에서 Codex가 실행되는지 확인하고, Codex 종료 후 같은 창에 Bash 프롬프트가 남는지 확인한다.
4. 다시 Mod+Enter → Enter로 새 터미널, Mod+Enter → b로 새 크롬 창이 열리는지 확인한다.
5. 각 실행 후 기본 모드로 돌아오는지, Mod+Enter → Escape는 창을 열지 않고 취소하는지 확인한다.
6. Mod+v → Mod+Enter → Enter는 위아래, Mod+g → Mod+Enter → b는 좌우로 배치되는지 확인한다.
7. 기본 모드의 Mod+b는 크롬을 실행하지 않는지 확인한다.

## 되돌리기

이 변경 커밋을 `git revert`한 뒤 설정을 리로드한다. 이미 열린 창은 그대로 남는다.
