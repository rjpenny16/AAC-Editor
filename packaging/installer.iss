#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId=AACEditor
AppName=AAC Editor
AppVersion={#AppVersion}
AppPublisher=Ryan Penny
AppPublisherURL=https://github.com/rjpenny16/AAC-Editor
AppSupportURL=https://github.com/rjpenny16/AAC-Editor/issues
DefaultDirName={autopf}\AAC Editor
DisableDirPage=yes
UsePreviousAppDir=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=AACEditor-{#AppVersion}-windows-x64-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\AAC Editor.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\AACEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AAC Editor"; Filename: "{app}\AAC Editor.exe"
Name: "{autodesktop}\AAC Editor"; Filename: "{app}\AAC Editor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\AAC Editor.exe"; Description: "Launch AAC Editor"; Flags: nowait postinstall skipifsilent
