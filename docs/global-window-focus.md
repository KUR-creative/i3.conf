# Mod+백틱으로 전역 이전 창 복귀
## 상태
i3-swap-focus 0.4.7을 pipx로 설치한 것을 확인하고 자동 시작과 단축키를 연결했다.
격리된 i3에서 검사하며 실제 세션의 reload·사용자 검수는 별도로 진행한다.

## 동작
- Mod+백틱은 워크스페이스·모니터와 관계없이 직전에 포커스했던 창으로 돌아간다.
- 다시 누르면 방금 떠난 창으로 돌아간다. 전체 이력을 순환하는 기능은 아니다.
- 대상 공간만 표시하며 반대 모니터를 정규 쌍으로 맞추지 않는다.
- Mod+Tab은 기존 이전 정규 쌍 복원, Mod+0은 F10+0 쌍 전환을 유지한다.
- Mod+Shift+백틱은 기존 Mod+Shift+0의 레이아웃 묶음 이동을 유지한다.
- 전역 복귀 자체는 ws의 JSON을 변경하지 않는다.

## 기존 도구 선택과 설치
i3 기본 focus next/prev는 컨테이너 트리 이동이며 전역 포커스 이력 복귀가 아니다.
마우스·키보드·외부 앱의 포커스 이벤트를 계속 듣는 기존 프로그램
[i3-swap-focus](https://pypi.org/project/i3-swap-focus/)를 사용한다.
별도 추적기를 직접 구현하거나 ws에 전역 이력을 추가하지 않는다.

다른 머신에 설치할 때:
```bash
sudo apt install pipx
pipx install i3-swap-focus==0.4.7
```
pipx가 프로그램과 i3ipc 의존성을 전용 가상 환경에 설치하고 ~/.local/bin에 노출한다.
시스템 Python에 pip로 직접 설치하지 않는다. 현재 머신에는 해당 경로가 PATH에 있다.

## 운영 구성
config.d/workspaces.conf에 다음을 둔다.
```i3
exec_always --no-startup-id flock -n -F "$XDG_RUNTIME_DIR/i3-swap-focus.lock" ~/.local/bin/i3-swap-focus
bindsym $mod+grave exec --no-startup-id pkill -USR1 -F "$XDG_RUNTIME_DIR/swap_focus.pid"
```
exec_always는 로그인·i3 재시작 때 실행된다. reload는 설정만 다시 읽으므로
새로 추가한 자동 시작 명령을 실행하지 않는다. flock -n은 이미 실행 중이면 종료하고,
-F는 별도 flock 부모 프로세스 없이 프로그램이 잠금을 유지하게 한다.
reload로 기존 추적기를 재시작하거나 이력을 초기화하지 않는다. 별도 systemd 서비스는 없다.
flock은 util-linux, pkill은 procps의 기존 도구다.

현재 세션에 처음 적용할 때는 설정을 reload한 다음 추적기도 한 번 시작한다:
```bash
i3-msg reload
i3-msg 'exec --no-startup-id flock -n -F "$XDG_RUNTIME_DIR/i3-swap-focus.lock" ~/.local/bin/i3-swap-focus'
```
이후 로그인에서는 자동 시작된다. 실행 중인 추적기는 reload해도 계속 실행된다.

## 상태와 한계
- 직전 두 창의 컨테이너 ID는 추적기 메모리에만 있다. 로그아웃·재부팅·프로세스 종료 시 사라진다.
- $XDG_RUNTIME_DIR/swap_focus.pid는 신호를 보낼 프로세스 ID다. 창 이력 파일이 아니다.
- $XDG_RUNTIME_DIR/i3-swap-focus.lock은 중복 실행 방지용 잠금 파일이다.
- 쌍별 상태인 $XDG_RUNTIME_DIR/i3-workspace-pair JSON과 독립적이다.
- 시작 직후에는 서로 다른 창 두 개를 포커스한 뒤 왕복을 확인한다.
- 이전 대상이 닫히면 복귀가 일어나지 않을 수 있다. 더 오래된 창을 찾아 건너뛰지는 않는다.
  이후 다른 창을 포커스하면 새 이력이 쌓인다.
- 마우스가 지나간 창과 쌍 전환 중간의 포커스 이벤트도 기록한다. 사용자 의도를 추측하지 않는다.

## 검증
자동 검사는 tests/global_window_focus_regression.py에서 설정의 실제 시작 명령을
격리 i3의 exec로 실행한다. 최초 reload만으로는 시작되지 않는 것도 검사한다.
같은 공간·다른 공간·다른 출력 왕복, Num Lock 두 상태, 마우스 포커스,
빈 이력·닫힌 대상·중복 시작·reload 이후 왕복과 ws JSON 보존을 확인한다.
테스트 프로세스는 격리된 Xvfb·i3와 전용 runtime을 사용한다.
/tmp의 설정 사본에서 백틱을 기존 ws 0 호출로 되돌리자 검사가 실패하는 것도 확인했다.
실패용 설정과 실행기는 저장소에 보존하지 않는다.

사용자 검수:
1. 처음 적용할 때는 위 reload와 추적기 시작 명령을 모두 실행한다.
2. F1의 창 A를 포커스하고 다른 공간의 창 B를 포커스한다.
3. Mod+백틱을 두 번 눌러 A → B로 왕복하는지 확인한다.
4. 같은 공간의 두 창과 마우스로 바꾼 포커스도 확인한다.
5. Mod+0·Mod+Tab·Mod+Shift+백틱이 기존 역할을 유지하는지 확인한다.
6. reload 후 다시 왕복하고, 재로그인 후 두 창을 포커스하여 새 이력을 확인한다.

## 최초 적용 실패 수정
2026-11-17 사용자 검수에서 복귀가 작동하지 않았다. 실제 세션에는 추적기와 PID 파일이
없었고 로그에는 pkill: pidfile not valid가 있었다. reload로 exec_always도 실행된다는
안내가 잘못되었다. 기존 검사는 추적기를 별도로 실행해 이 설치 절차의 누락을 검출하지 못했다.
현재 세션의 추적기를 명시적으로 시작했고, 문서와 회귀 검사를 위 절차로 수정했다.
