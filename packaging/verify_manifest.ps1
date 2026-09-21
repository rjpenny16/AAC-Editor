param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,

    # Which privilege the build intended to embed. "asinvoker" is the unsigned
    # default; "uiaccess" is only ever asked for by a signing build.
    [ValidateSet("asinvoker", "uiaccess")]
    [string]$Expect = "asinvoker"
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

# Administrator is never requested up front, whichever manifest was embedded.
# Live Grid 3 editing asks for elevation at the moment it needs it, so that
# everything else in the app runs at the privilege the user started it with.
if ($manifest -notmatch 'requestedExecutionLevel\s+level="asInvoker"') {
    throw "The embedded manifest does not request asInvoker: $resolved"
}

$wantsUiAccess = $manifest -match 'requestedExecutionLevel\s+level="asInvoker"\s+uiAccess="true"'
$refusesUiAccess = $manifest -match 'requestedExecutionLevel\s+level="asInvoker"\s+uiAccess="false"'

if (-not ($wantsUiAccess -or $refusesUiAccess)) {
    throw "The embedded manifest does not state uiAccess either way: $resolved"
}

# The invariant, checked whatever -Expect said: Windows refuses to start a
# uiAccess="true" executable that does not carry a trusted Authenticode
# signature, so shipping one unsigned produces a binary nobody can launch.
# This runs after signing in build.ps1 for exactly that reason.
if ($wantsUiAccess) {
    $signature = Get-AuthenticodeSignature -LiteralPath $resolved
    if ($signature.Status -ne "Valid") {
        throw ("The embedded manifest requests uiAccess but the file is not validly " +
               "signed ($($signature.Status)), and Windows would refuse to start it: $resolved")
    }
}

$embedded = if ($wantsUiAccess) { "uiaccess" } else { "asinvoker" }
if ($embedded -ne $Expect) {
    throw "Expected the $Expect manifest but the binary embeds $embedded`: $resolved"
}

Write-Output "Verified embedded asInvoker manifest ($embedded): $resolved"
