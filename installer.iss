; 书画室本地看板 —— Windows 安装包
; 由 build.py 自动调用；也可以在 Inno Setup 里直接打开编译。
; 产物：installer_output\书画室看板-安装程序.exe（单个文件，离线可用）

#define AppName "书画室看板"
#define AppVersion "1.0.0"
#define AppExe "书画室看板.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; 装到 Program Files 需要管理员权限；数据不放这里，放用户文档目录
PrivilegesRequired=admin
OutputDir=installer_output
OutputBaseFilename=书画室看板-安装程序
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
; 语音模型 200 多 MB，压缩耗时较长属正常
DiskSpanning=no
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
Source: "dist\书画室看板\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Dirs]
; 数据目录要可写：装在 Program Files 时普通用户默认写不进去，这里显式放开
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\backups"; Permissions: users-modify

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动{#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只删程序，不删数据 —— 卸载不该带走学员资料
Type: filesandordirs; Name: "{app}\_internal"

[Messages]
chinese.WelcomeLabel2=即将安装 {#AppName}。%n%n本程序完全离线运行，不需要联网。%n安装后数据保存在程序目录下的 data 文件夹。
