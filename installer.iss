[Setup]
AppName=Supply Chain Sparks
AppVersion=0.1.0
DefaultDirName={localappdata}\SupplyChainSparks
DefaultGroupName=Supply Chain Sparks
PrivilegesRequired=lowest
OutputBaseFilename=SupplyChainSparks-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\SupplyChainSparks\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Supply Chain Sparks"; Filename: "{app}\SupplyChainSparks.exe"
Name: "{commondesktop}\Supply Chain Sparks"; Filename: "{app}\SupplyChainSparks.exe"

[Run]
Filename: "{app}\SupplyChainSparks.exe"; Description: "Launch Supply Chain Sparks"; Flags: nowait postinstall skipifsilent
