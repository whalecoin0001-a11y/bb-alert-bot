' 배치 파일을 콘솔창 없이(숨김) 실행한다. 작업 스케줄러 액션에서 호출용.
' 사용법: wscript.exe run_hidden.vbs "대상.bat"
Set objShell = CreateObject("WScript.Shell")
objShell.Run """" & WScript.Arguments(0) & """", 0, True
