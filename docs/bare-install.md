# Bare ServiceReady installation

Since 0.6.0 every new installation starts with Home, accounts, and Administration.
No optional addon code is installed. Upload separate `.sraddon` files to add
features. See [Addon packages](addon-packages.md) for package files and removal.

On a fresh Alpine/OpenRC VM, clone the repository's main branch and run:

```sh
./install-alpine.sh --bare
```

The installer asks for the portal URL and first administrator credentials.
Alpine accounts remain the authentication source. `--bare` refuses an existing
configured installation. Run the installer without that flag for an upgrade;
existing configuration and saved data are preserved. Old bundled-module flags
no longer install features; upload matching packages after upgrading to 0.6.0.

For a local development instance:

```sh
cp config.bare.json config.json
python3 -m voiceservices --config config.json create-user admin --admin
python3 -m voiceservices --config config.json serve
```

The local test preview uses a separate database at port 8081, with temporary
admin / admin credentials. The Alpine installer does not use that password.

Install Downloads from its package, publish a test link, then uninstall it. The
installed directory is deleted and the menu/routes disappear. Reinstall the same
package to verify saved data remains. Repeat with the other packages and restart
the portal to check persistence. Installing PXE/FTP does not enable networking;
configure those listeners separately on your deployment network.
