# Print Screen 영역 캡처
## 설정
사용자가 Flameshot을 설치한 뒤 Print Screen 단축키 연결을 요청했다.
설치된 버전은 13.3.0이며 config.d/shortcuts.conf에 다음을 추가했다.
```i3
bindsym --release Print exec --no-startup-id flameshot gui
```
키를 놓은 뒤 영역 선택 GUI를 연다. 별도 스크립트나 자동 시작 항목은 필요 없다.

## 적용과 사용자 검수
1. i3-msg reload를 실행한다.
2. Print Screen을 누르고 놓으면 영역 선택 화면이 나오는지 확인한다.
3. 영역을 드래그하고 클립보드 복사 또는 파일 저장을 확인한다.
4. 다시 실행하여 Escape로 취소되는지 확인한다.
설정 문법과 중복 바인딩은 확인하며 실제 GUI 검수는 사용자에게 맡긴다.

## 창 단위 캡처
현재 Flameshot 도움말에는 활성 창을 직접 캡처하는 옵션이 없다.
gui는 영역 선택, screen은 모니터, full은 전체 모니터 캡처다.
창 단위 캡처는 i3에서도 외부 도구로 가능하다. 예를 들어
[scrot](https://github.com/resurrecting-open-source-projects/scrot/blob/master/man/scrot.txt)의
-u/--focused는 현재 포커스한 창을 캡처한다. 필요하면 별도 설치 후 Alt+Print 같은 키에
연결할 수 있다. 이번 변경에는 설치하거나 바인딩을 추가하지 않았다.
