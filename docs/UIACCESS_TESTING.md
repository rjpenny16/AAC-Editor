# Development-only UIAccess testing

Windows grants UIAccess only to an Authenticode-signed application trusted by
the computer and installed in a secure location such as Program Files. The
production certificate is not part of this repository. The build remains
unsigned unless signing is explicitly requested.

Use the following only on an isolated development computer. Package CI performs
the equivalent operation on a disposable GitHub-hosted runner, removes the test
certificate afterward, and never publishes its artifacts. A public release
must never use this certificate path.

1. Create a temporary code-signing certificate in your personal certificate
   store:

   ```powershell
   $testCert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=AAC Editor UIAccess Development Only" -CertStoreLocation Cert:\CurrentUser\My
   Export-Certificate -Cert $testCert -FilePath "$env:TEMP\aac-editor-uiaccess-dev.cer"
   ```

2. On the test computer only, review the certificate thumbprint, then explicitly
   trust its public certificate. Importing into the machine root store requires
   administrator approval:

   ```powershell
   $testCert.Thumbprint
   Import-Certificate -FilePath "$env:TEMP\aac-editor-uiaccess-dev.cer" -CertStoreLocation Cert:\LocalMachine\Root
   ```

3. Request signing by thumbprint. The script never creates, imports, or trusts a
   certificate. Disable timestamping for this temporary certificate:

   ```powershell
   $env:AAC_EDITOR_SIGNING_THUMBPRINT = $testCert.Thumbprint
   $env:AAC_EDITOR_TIMESTAMP_URL = "none"
   .\packaging\build.ps1 -Version dev -Sign
   ```

4. Install the generated setup executable and test only the copy beneath
   Program Files. A copied or portable executable does not provide UIAccess.

5. Reverse the test setup after uninstalling AAC Editor. Verify the thumbprint
   before each removal:

   ```powershell
   Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\Root |
     Where-Object Thumbprint -eq $testCert.Thumbprint |
     Format-List Subject, Thumbprint, PSParentPath
   Remove-Item "Cert:\CurrentUser\My\$($testCert.Thumbprint)"
   Remove-Item "Cert:\LocalMachine\Root\$($testCert.Thumbprint)"
   Remove-Item "$env:TEMP\aac-editor-uiaccess-dev.cer"
   ```

Production builds use SignPath's official GitHub integration and a trusted,
timestamped certificate. Never publish an artifact signed by this temporary
certificate.
