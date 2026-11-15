# 개인 앱 실행 단축키 분리

## 변경

- 개인 앱 실행 단축키를 `config.d/shortcuts.conf`에 모으고 메인 `config`에서 명시적으로 include한다.
- 기존 Mod+Enter의 `ptyxis --new-window`를 base.conf에서 옮긴다.
- Mod+b에 `google-chrome-stable --new-window`를 연결한다.

## 검증

- `i3 -C -c ~/.config/i3/config`: 통과. 샌드박스의 런타임 로그 경로 제한 때문에 임시 XDG_RUNTIME_DIR을 사용했다.
- Mod+Return과 Mod+b는 각각 한 번만 정의되어 있다.
- `git diff --check`: 통과.
- 실제 키 입력은 사용자 검수 대기.

## 적용과 검수

1. Mod+Shift+c로 설정을 리로드한다.
2. Mod+Enter로 새 터미널 창이 열리는지 확인한다.
3. Mod+b로 크롬 창이 열리는지 확인하고, 다시 눌러 새 창이 추가되는지 확인한다.

## 되돌리기

이 변경 커밋을 `git revert`한 뒤 설정을 리로드한다. 이미 열린 창은 그대로 남는다.
