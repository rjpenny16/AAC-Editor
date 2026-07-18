param(
    [Parameter(Mandatory = $true)]
    [string]$Executable
)

$ErrorActionPreference = "Stop"
$resolved = (Resolve-Path -LiteralPath $Executable).Path

Add-Type @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class EmbeddedManifest {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr LoadLibraryEx(string path, IntPtr file, uint flags);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr FindResource(IntPtr module, IntPtr name, IntPtr type);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr LoadResource(IntPtr module, IntPtr resource);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr LockResource(IntPtr resource);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern uint SizeofResource(IntPtr module, IntPtr resource);
    [DllImport("kernel32.dll")]
    static extern bool FreeLibrary(IntPtr module);

    public static byte[] Read(string path) {
        IntPtr module = LoadLibraryEx(path, IntPtr.Zero, 0x2);
        if (module == IntPtr.Zero) throw new Win32Exception();
        try {
            IntPtr found = FindResource(module, (IntPtr)1, (IntPtr)24);
            if (found == IntPtr.Zero) throw new Exception("No embedded application manifest was found.");
            uint size = SizeofResource(module, found);
            IntPtr loaded = LoadResource(module, found);
            IntPtr data = LockResource(loaded);
            byte[] bytes = new byte[size];
            Marshal.Copy(data, bytes, 0, (int)size);
            return bytes;
        } finally {
            FreeLibrary(module);
        }
    }
}
"@

$bytes = [EmbeddedManifest]::Read($resolved)
$manifest = [Text.Encoding]::UTF8.GetString($bytes).Trim([char]0, [char]0xFEFF)
if ($manifest -notmatch 'requestedExecutionLevel\s+level="asInvoker"\s+uiAccess="true"') {
    throw "The embedded manifest does not request asInvoker with uiAccess=true: $resolved"
}

Write-Output "Verified embedded asInvoker/uiAccess manifest: $resolved"
