Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Loyiha papkasi
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Python yo'lini topish funksiyasi
Function FindPython()
    Dim localApp, versions, i, path
    localApp = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

    ' PATH orqali pythonw topish
    On Error Resume Next
    Dim tmpFile
    tmpFile = WshShell.ExpandEnvironmentStrings("%TEMP%") & "\py_path.txt"
    WshShell.Run "cmd /c where pythonw.exe > """ & tmpFile & """ 2>nul", 0, True
    If fso.FileExists(tmpFile) Then
        Dim ts
        Set ts = fso.OpenTextFile(tmpFile, 1)
        If Not ts.AtEndOfStream Then
            path = Trim(ts.ReadLine())
            ts.Close
            fso.DeleteFile tmpFile
            If fso.FileExists(path) Then
                FindPython = path
                Exit Function
            End If
        End If
        fso.DeleteFile tmpFile
    End If
    On Error GoTo 0

    ' Umumiy Python versiyalarini tekshirish (yangi -> eski)
    versions = Array("Python314", "Python313", "Python312", "Python311", "Python310", "Python39", "Python38")
    For i = 0 To UBound(versions)
        path = localApp & "\Programs\Python\" & versions(i) & "\pythonw.exe"
        If fso.FileExists(path) Then
            FindPython = path
            Exit Function
        End If
    Next

    ' python.exe (non-w) variantlarini tekshirish
    For i = 0 To UBound(versions)
        path = localApp & "\Programs\Python\" & versions(i) & "\python.exe"
        If fso.FileExists(path) Then
            FindPython = path
            Exit Function
        End If
    Next

    ' System-wide o'rnatish
    Dim sysRoot
    sysRoot = WshShell.ExpandEnvironmentStrings("%SystemDrive%")
    For i = 0 To UBound(versions)
        path = sysRoot & "\Python\" & versions(i) & "\pythonw.exe"
        If fso.FileExists(path) Then
            FindPython = path
            Exit Function
        End If
    Next

    FindPython = ""
End Function

Dim pythonPath
pythonPath = FindPython()

If pythonPath = "" Then
    MsgBox "Python topilmadi!" & vbCrLf & vbCrLf & _
           "Python o'rnatish uchun:" & vbCrLf & _
           "https://www.python.org/downloads/" & vbCrLf & vbCrLf & _
           "O'rnatgandan so'ng qayta urinib ko'ring.", _
           vbCritical, "SlapWin - Xatolik"
    WScript.Quit
End If

' Dasturni ishga tushirish (konsolsiz)
WshShell.Run """" & pythonPath & """ """ & scriptDir & "\slapwin.py""", 0, False
