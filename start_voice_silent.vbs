Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
pyw312 = localAppData & "\Programs\Python\Python312\pythonw.exe"

If fso.FileExists(pyw312) Then
    runnerCmd = """" & pyw312 & """"
Else
    runnerCmd = "pythonw.exe"
End If

WshShell.Run runnerCmd & " """ & scriptDir & "\main.py""", 0, False

