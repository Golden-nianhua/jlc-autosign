$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "main.py"
$log_file = Join-Path $root "autosign.log"

# 任务每天 00:01 触发，并由 Windows 在随后 59 分钟内随机执行。
$trigger = New-ScheduledTaskTrigger -Daily -At 12:01AM -RandomDelay (New-TimeSpan -Minutes 59)
$command = "& '$python' '$script' *>> '$log_file'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$command`""

Register-ScheduledTask -TaskName "JLC Auto Sign" -Action $action -Trigger $trigger -Force
