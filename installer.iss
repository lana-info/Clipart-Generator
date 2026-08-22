#define AppName "Vibix Images"
#ifndef AppVersion
  #error "AppVersion must be supplied from release/VERSION.txt by the release build"
#endif
#define AppPublisher "Vibix"
#define AppExeName "Vibix Images.exe"

[Setup]
AppId={{B8D6B3F4-4E5F-4B6E-9D13-9A8E3B2F3C7A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
SetupIconFile=assets\vibix-images.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
OutputDir=release
OutputBaseFilename=VibixImages-Setup-{#AppVersion}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"; Flags: unchecked

[Files]
Source: "dist\Vibix Images\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "build-prerequisites\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: dontcopy

[InstallDelete]
; PyInstaller native libraries must be replaced as one coherent set on upgrade.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\realesrgan-ncnn-vulkan-20211212-windows"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  ExtractTemporaryFile('vc_redist.x64.exe');
  WizardForm.StatusLabel.Caption := 'Установка системных компонентов Microsoft...';
  if not Exec(
    ExpandConstant('{tmp}\vc_redist.x64.exe'),
    '/install /quiet /norestart',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Result := 'Не удалось запустить установку системных компонентов Microsoft.';
    Exit;
  end;

  if ResultCode = 3010 then
  begin
    NeedsRestart := True;
    Result := 'Для завершения установки системных компонентов Microsoft требуется перезагрузка Windows. Перезагрузите компьютер и затем снова запустите установщик Vibix Images.';
  end
  else if (ResultCode <> 0) and (ResultCode <> 1638) then
    Result := 'Не удалось установить системные компоненты Microsoft (код ' +
      IntToStr(ResultCode) + ').';
end;
