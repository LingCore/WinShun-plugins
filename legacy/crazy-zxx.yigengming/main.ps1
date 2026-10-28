param(
    [switch]$Ui,
    [switch]$Validate,
    [string]$Screenshot,
    [string]$RenderDemo,
    [ValidateSet('System','Light','Dark')][string]$Theme = 'System'
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$errorWriter = New-Object System.IO.StreamWriter([Console]::OpenStandardError(), [Console]::OutputEncoding)
$errorWriter.AutoFlush = $true
[Console]::SetError($errorWriter)
$OutputEncoding = [Console]::OutputEncoding
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) ('WinShun-YiGengMing-' + [Guid]::NewGuid().ToString('N'))
$domain = $null
$provider = $null
$result = 1
try {
    [System.IO.Directory]::CreateDirectory($temporary) | Out-Null
    Add-Type -AssemblyName Microsoft.CSharp
    $provider = New-Object Microsoft.CSharp.CSharpCodeProvider
    $parameters = New-Object System.CodeDom.Compiler.CompilerParameters
    $parameters.GenerateExecutable = $false
    $parameters.GenerateInMemory = $false
    $parameters.OutputAssembly = Join-Path $temporary 'YiGengMing.Runtime.dll'
    $parameters.TempFiles = New-Object System.CodeDom.Compiler.TempFileCollection($temporary, $false)
    $parameters.CompilerOptions = '/optimize+ /codepage:65001 /utf8output'
    foreach ($reference in @('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll')) {
        $parameters.ReferencedAssemblies.Add($reference) | Out-Null
    }
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'src') -Filter '*.cs' -File | ForEach-Object FullName)
    if ($Validate) {
        $sources += Join-Path $PSScriptRoot 'tests\CoreTests.cs'
        $sources += Join-Path $PSScriptRoot 'tests\UiTests.cs'
    }
    $compiled = $provider.CompileAssemblyFromFile($parameters, [string[]]$sources)
    if ($compiled.Errors.HasErrors) {
        foreach ($entry in $compiled.Errors) { [Console]::Error.WriteLine($entry.ToString()) }
        throw '易更名源码编译失败；请确认已安装 .NET Framework 4.8。'
    }
    $setup = New-Object System.AppDomainSetup
    $setup.ApplicationBase = $temporary
    $setup.ShadowCopyFiles = 'true'
    $setup.CachePath = Join-Path $temporary 'cache'
    $setup.ConfigurationFile = Join-Path $PSScriptRoot 'runtime.config'
    $setup.TargetFrameworkName = '.NETFramework,Version=v4.8'
    $domain = [AppDomain]::CreateDomain('YiGengMing', $null, $setup)
    # Load our just-compiled bytes rather than using LoadFrom with a sandbox-virtualized
    # temp path. This needs no remote-source trust or changes to Windows security settings.
    $assemblyBytes = [System.IO.File]::ReadAllBytes($parameters.OutputAssembly)
    $assembly = [System.Reflection.Assembly]::Load($assemblyBytes)
    $hostObject = $domain.CreateInstanceAndUnwrap($assembly.FullName, 'WinShun.BatchRenamer.CommunityHost')
    $hostObject.Initialize($PSScriptRoot)
    if ($Validate) {
        $result = $hostObject.Validate($Screenshot)
    }
    else {
        [string[]]$arguments = @('--serve')
        if ($Ui) { $arguments = @('--ui') }
        elseif ($RenderDemo) { $arguments = @('--render-demo', [System.IO.Path]::GetFullPath($RenderDemo), $Theme) }
        $result = $hostObject.Run($arguments)
    }
}
catch { [Console]::Error.WriteLine($_.Exception.ToString()) }
finally {
    if ($domain) { [AppDomain]::Unload($domain) }
    if ($provider) { $provider.Dispose() }
    # Only this invocation's random compiler directory is removed, never user-selected paths.
    try { if ([System.IO.Directory]::Exists($temporary)) { [System.IO.Directory]::Delete($temporary, $true) } }
    catch { [Console]::Error.WriteLine('无法清理临时编译目录：' + $temporary) }
}
exit $result
