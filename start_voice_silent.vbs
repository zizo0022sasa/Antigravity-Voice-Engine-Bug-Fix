Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
py312 = localAppData & "\Programs\Python\Python312\pythonw.exe"

If fso.FileExists(py312) Then
    pythonwCmd = """" & py312 & """"
Else
    pythonwCmd = "pythonw.exe"
End If

WshShell.Run pythonwCmd & " """ & scriptDir & "\main.py""", 0, False
