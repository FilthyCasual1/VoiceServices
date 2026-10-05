# Bare ServiceReady installation

The bare profile starts with Home, authentication, My Account, and Administration.
No optional modules are enabled. Addon implementations remain bundled in the
release so Administration > Addons can install and remove them without a separate
package download. Installation here means enabling a bundled module, not fetching
arbitrary third-party code.

On a fresh Alpine/OpenRC VM, clone the repository, switch to `initial-portal`, and run:

```sh
./install-alpine.sh --bare
```

The installer asks for the portal URL and initial administrator credentials.
Alpine accounts remain the authentication source. The installer refuses `--bare`
on an existing configured installation, protecting its accounts and module state.
Regular upgrades preserve configuration and addon choices.

For a local development instance:

```sh
cp config.bare.json config.json
python3 -m voiceservices --config config.json create-user admin --admin
python3 -m voiceservices --config config.json serve
```

Use a separate working directory/database from the full deployment. Select
Administration > Addons, install Downloads, publish a test link, then remove it.
The menu and routes disappear. Reinstall it to confirm the link remains. Repeat
with Voice Services, Server Management, PXE, and FTP Update Repository. Installing
PXE or FTP does not enable their network listeners; configure those separately.
Restart the portal after installing and removing modules to verify persistence.

The local bare test preview uses a separate database and port 8081. Its temporary
administrator login is admin / admin. The Alpine installer does not use that password.
