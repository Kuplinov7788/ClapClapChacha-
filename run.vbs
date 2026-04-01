Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Loyiha papkasi
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Python yo'li
pythonPath = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe"

' Agar pythonw topilmasa, oddiy python ishlatamiz
If Not fso.FileExists(pythonPath) Then
    pythonPath = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\python.exe"
End If

' Dasturni ishga tushirish (konsolsiz)
WshShell.Run """" & pythonPath & """ """ & scriptDir & "\slapwin.py""", 0, True

' Dastur yopilganda loyiha papkasini ochish
WshShell.Run "explorer.exe """ & scriptDir & """", 1, False
