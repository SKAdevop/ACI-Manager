[Setup]
AppName=ACI Manager ToolSet
AppVersion=1.1.0
DefaultDirName={autopf}\ACI Manager ToolSet
DefaultGroupName=ACI Manager ToolSet
OutputBaseFilename=ACIManagerSetup
Compression=lzma
SolidCompression=yes
SetupIconFile=ACI Manager.ico

[Files]
Source: "dist\aci-proxy.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ACI Manager ToolSet"; Filename: "{app}\aci-proxy.exe"
Name: "{commondesktop}\ACI Manager ToolSet"; Filename: "{app}\aci-proxy.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\aci-proxy.exe"; Description: "Launch ACI Manager ToolSet"; Flags: nowait postinstall skipifsilent

[Code]
var
  APICPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  APICPage := CreateInputQueryPage(wpSelectDir,
    'APIC Configuration', 
    'Specify your Cisco APIC Server URL',
    'Please enter the full URL of your Cisco APIC controller (e.g. https://apic.company.local):');
  
  APICPage.Add('APIC Server URL:', False);
  APICPage.Values[0] := 'https://tpaci.bswhealth.org';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigContent: String;
  ConfigPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigPath := ExpandConstant('{app}\config.json');
    ConfigContent := '{"apic_url": "' + APICPage.Values[0] + '"}';
    SaveStringToFile(ConfigPath, ConfigContent, False);
  end;
end;
