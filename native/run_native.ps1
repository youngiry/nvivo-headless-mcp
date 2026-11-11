$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$p = $env:NVIVO_NATIVE_ROOT
$v = $env:NVIVO_INSTALL_DIR
if (-not $v -or -not (Test-Path -LiteralPath "$v/NVivo.exe")) { throw "Set NVIVO_INSTALL_DIR to your installed NVivo 15 directory" }
$t = $env:NVIVO_NATIVE_TEMP
New-Item -ItemType Directory -Path $t | Out-Null
Copy-Item -LiteralPath "$v/NVivo.exe" -Destination "$t/NVivoReference.dll"
Add-Type -Path @("$p/native/IsolatedRunner.cs", "$p/native/FrameworkRuntimeHost.cs") -OutputAssembly "$t/IsolatedRunner.dll" -ReferencedAssemblies System.dll,System.Core.dll
Add-Type -Path "$p/native/NativeHeadless.cs" -OutputAssembly "$t/NativeHeadless.dll" -ReferencedAssemblies System.dll,System.Core.dll,System.Configuration.dll,System.Data.dll,System.Web.Extensions.dll,System.Xml.dll
Add-Type -Path "$p/native/NativeConverterController.cs" -OutputAssembly "$t/NativeConverterController.dll" -ReferencedAssemblies @('System.dll', "$v/QSR.NVivo.Common.Business.dll", "$v/QSR.NVivo.Common.Data.dll")
Add-Type -Path "$p/native/HeadlessSourceImporter.cs" -OutputAssembly "$t/HeadlessSourceImporter.dll" -ReferencedAssemblies @('System.dll', 'System.Core.dll', "$t/NVivoReference.dll", "$v/QSR.NVivo.Common.Business.dll", "$v/QSR.NVivo.Common.Data.dll")
[void][Reflection.Assembly]::LoadFrom("$t/IsolatedRunner.dll")
$log = [IO.Path]::ChangeExtension($env:NVIVO_NATIVE_ARGUMENT, '.native.log')
$result = [IsolatedRunner]::RunManaged("$t/NativeHeadless.dll", $log, [string[]]@($env:NVIVO_NATIVE_MODE, $env:NVIVO_NATIVE_TARGET, $env:NVIVO_NATIVE_ARGUMENT))
Write-Output "Native service exit=$result"
exit $result
