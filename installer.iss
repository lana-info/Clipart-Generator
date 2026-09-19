#ifdef AcceptanceBuild
  #define AppName "Vibix Studio Test"
  #define AppId "{{617F3BD6-AB32-4544-AC32-FF055B7F5F8C}"
#else
  #define AppName "Vibix Images"
  #define AppId "{{B8D6B3F4-4E5F-4B6E-9D13-9A8E3B2F3C7A}"
#endif
#ifndef AppVersion
  #error "AppVersion must be supplied from release/VERSION.txt by the release build"
#endif
#define AppPublisher "Vibix"
#define AppExeName "Vibix Images.exe"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
SetupIconFile=assets\vibix-images.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma
SolidCompression=yes
; Inno Setup 6.7+ supplies the built-in high-DPI dark Polar style.
WizardStyle=modern dark polar includetitlebar hidebevels
WizardSizePercent=125,120
WizardResizable=no
DisableWelcomePage=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
WizardImageFile=assets\installer-wizard-hq.png
WizardBackColor=#101827
WizardImageBackColor=#101827
WizardKeepAspectRatio=yes
OutputDir=release
#ifdef AcceptanceBuild
OutputBaseFilename=VibixImages-Test-Setup-{#AppVersion}
#else
OutputBaseFilename=VibixImages-Setup-{#AppVersion}
#endif
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
ButtonNext=Продолжить
ButtonInstall=Установить
ButtonFinish=Готово
WelcomeLabel1=1 из 3 · Добро пожаловать%n%n{#AppName}
WelcomeLabel2=Массовая генерация изображений в нейросетях, в том числе клипартов.%n%n• Создать клипарт%n• Создать Pinterest-пины%n• Обработать изображения%n%nНажмите «Продолжить», чтобы установить приложение.
WizardSelectDir=2 из 3 · Установка
SelectDirDesc=Выберите папку для {#AppName}.
WizardSelectTasks=2 из 3 · Установка
SelectTasksDesc=Выберите дополнительные параметры.
WizardInstalling=2 из 3 · Установка
InstallingLabel=Подождите, пока {#AppName} устанавливается на компьютер.
FinishedHeadingLabel=3 из 3 · Готово
FinishedLabel={#AppName} установлен.%n%nЗапустите приложение и активируйте лицензию, чтобы начать массовую генерацию и обработку изображений.
ClickFinish=Нажмите «Готово», чтобы закрыть установщик.

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
#ifdef AcceptanceBuild
const
  ProductionUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B8D6B3F4-4E5F-4B6E-9D13-9A8E3B2F3C7A}_is1';
  AcceptanceUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{617F3BD6-AB32-4544-AC32-FF055B7F5F8C}_is1';

function SameInstallDir(const LeftPath, RightPath: String): Boolean;
begin
  Result := PathSame(
    RemoveBackslashUnlessRoot(LeftPath),
    RemoveBackslashUnlessRoot(RightPath)
  );
end;

function RegistryInstallDirMatches(
  RootKey: HKEY;
  const UninstallKey, SelectedDir: String
): Boolean;
var
  InstallLocation: String;
begin
  Result :=
    RegQueryStringValue(RootKey, UninstallKey, 'InstallLocation', InstallLocation) and
    SameInstallDir(InstallLocation, SelectedDir);
end;

function IsRegisteredInstallDir(
  const SelectedDir, UninstallKey: String
): Boolean;
begin
  Result :=
    RegistryInstallDirMatches(HKEY_LOCAL_MACHINE_64, UninstallKey, SelectedDir) or
    RegistryInstallDirMatches(HKEY_LOCAL_MACHINE_32, UninstallKey, SelectedDir) or
    RegistryInstallDirMatches(HKEY_CURRENT_USER_64, UninstallKey, SelectedDir) or
    RegistryInstallDirMatches(HKEY_CURRENT_USER_32, UninstallKey, SelectedDir);
end;

function IsRegisteredAcceptanceInstallDir(const SelectedDir: String): Boolean;
begin
  Result := IsRegisteredInstallDir(SelectedDir, AcceptanceUninstallKey);
end;

function AcceptanceInstallConflict(const SelectedDir: String): String;
begin
  Result := '';

  if SameInstallDir(SelectedDir, ExpandConstant('{autopf}\Vibix Images')) then
  begin
    Result := 'Тестовую сборку нельзя установить в стандартную папку Vibix Images. Выберите отдельную папку для Vibix Studio Test.';
    Exit;
  end;

  if IsRegisteredInstallDir(SelectedDir, ProductionUninstallKey) then
  begin
    Result := 'В выбранной папке зарегистрирована рабочая установка Vibix Images. Выберите отдельную папку для Vibix Studio Test.';
    Exit;
  end;

  if FileExists(AddBackslash(SelectedDir) + '{#AppExeName}') and
     not IsRegisteredAcceptanceInstallDir(SelectedDir) then
    Result := 'В выбранной папке уже находится Vibix Images. Чтобы не перезаписать рабочую установку, выберите отдельную папку для Vibix Studio Test.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Conflict: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Conflict := AcceptanceInstallConflict(WizardDirValue);
    if Conflict <> '' then
    begin
      SuppressibleMsgBox(Conflict, mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;
#endif

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardForm.Caption := '{#AppName} — 1 из 3 · Добро пожаловать'
  else if CurPageID = wpFinished then
    WizardForm.Caption := '{#AppName} — 3 из 3 · Готово'
  else
    WizardForm.Caption := '{#AppName} — 2 из 3 · Установка';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
#ifdef AcceptanceBuild
  Result := AcceptanceInstallConflict(WizardDirValue);
  if Result <> '' then
    Exit;
#endif
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
    Result := 'Для завершения установки системных компонентов Microsoft требуется перезагрузка Windows. Перезагрузите компьютер и затем снова запустите установщик {#AppName}.';
  end
  else if (ResultCode <> 0) and (ResultCode <> 1638) then
    Result := 'Не удалось установить системные компоненты Microsoft (код ' +
      IntToStr(ResultCode) + ').';
end;
