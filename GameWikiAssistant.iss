; Inno Setup Script for GameWiki Assistant
; This script creates a professional installer for the application

#define MyAppName "GameWiki Assistant"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "GameWiki Team"
#define MyAppURL "https://github.com/yourusername/gamewiki"
#define MyAppExeName "GameWikiAssistant.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application
AppId={{8F7A9E2C-4B3D-4E6A-9C1F-2A3B4C5D6E7F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Privileges - use lowest to avoid UAC prompts when possible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=GameWikiAssistant_Setup
SetupIconFile=src\game_wiki_tooltip\assets\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Enable 64-bit mode on 64-bit systems
ArchitecturesInstallIn64BitMode=x64
; Uninstaller
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Signing (if certificate available)
; SignTool=mysigntool
; SignedUninstaller=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main application files (OneDir mode)
Source: "dist\GameWikiAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; WebView2 Runtime installer
Source: "GameWikiAssistant_Portable_onedir\runtime\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; Install WebView2 Runtime if not already installed (silent install)
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; Check: not IsWebView2Installed; Flags: waituntilterminated
; Launch application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Check if WebView2 Runtime is installed
function IsWebView2Installed: Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
            RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
  
  if Result then
    Log('WebView2 Runtime is installed: ' + Version)
  else
    Log('WebView2 Runtime is not installed');
end;

// Initialize setup
function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // Check Windows version (Windows 10 or higher recommended)
  if not IsWindows10OrNewer then
  begin
    if MsgBox('This application works best on Windows 10 or higher. Continue installation?', 
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

// Check if Windows 10 or newer
function IsWindows10OrNewer: Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := (Version.Major >= 10);
end;

// Custom page to show important information
procedure CreateCustomPages;
var
  InfoPage: TWizardPage;
  InfoLabel: TNewStaticText;
begin
  InfoPage := CreateCustomPage(wpSelectDir, 'Important Information', 
    'Please read the following information before continuing.');
  
  InfoLabel := TNewStaticText.Create(InfoPage);
  InfoLabel.Parent := InfoPage.Surface;
  InfoLabel.Top := 0;
  InfoLabel.Left := 0;
  InfoLabel.Width := InfoPage.Surface.Width;
  InfoLabel.Height := 150;
  InfoLabel.AutoSize := False;
  InfoLabel.WordWrap := True;
  InfoLabel.Caption := 
    'GameWiki Assistant Requirements:' + #13#10 + #13#10 +
    '• Windows 10 or higher (Windows 11 recommended)' + #13#10 +
    '• Microsoft Edge WebView2 Runtime (will be installed automatically)' + #13#10 +
    '• Internet connection for AI features' + #13#10 +
    '• API keys for full functionality (can be configured later)' + #13#10 + #13#10 +
    'The installer will automatically install WebView2 Runtime if not present.';
end;

procedure InitializeWizard;
begin
  CreateCustomPages;
end;

// Uninstaller - clean up user data if requested
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DeleteUserData: Integer;
  UserDataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Ask if user wants to delete configuration files
    DeleteUserData := MsgBox('Do you want to delete your configuration and settings?' + #13#10 + 
                            'This will remove all API keys and preferences.',
                            mbConfirmation, MB_YESNO);
    
    if DeleteUserData = IDYES then
    begin
      UserDataPath := ExpandConstant('{userappdata}\game_wiki_tooltip');
      if DirExists(UserDataPath) then
      begin
        DelTree(UserDataPath, True, True, True);
        Log('Deleted user data directory: ' + UserDataPath);
      end;
    end;
  end;
end;

[Registry]
; Register application for Windows
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[Messages]
; Custom messages
BeveledLabel=GameWiki Assistant Installer

[CustomMessages]
; Chinese translations
chinesesimplified.BeveledLabel=游戏维基助手安装程序