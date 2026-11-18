Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

' Dynamically select a Python 3.10+ interpreter that has sounddevice installed
runnerCmd = ""
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
pyRoot = localAppData & "\Programs\Python"

If fso.FolderExists(pyRoot) Then
    For Each subFolder In fso.GetFolder(pyRoot).SubFolders
        candPy = subFolder.Path & "\python.exe"
        candPyw = subFolder.Path & "\pythonw.exe"
        If fso.FileExists(candPy) And fso.FileExists(candPyw) Then
            rc = WshShell.Run("""" & candPy & """ -c ""import sounddevice, numpy""", 0, True)
            If rc = 0 Then
                runnerCmd = """" & candPyw & """"
                Exit For
            End If
        End If
    Next
End If

If runnerCmd = "" Then
    runnerCmd = "pythonw.exe"
End If

WshShell.Run runnerCmd & " """ & scriptDir & "\main.py""", 0, False
