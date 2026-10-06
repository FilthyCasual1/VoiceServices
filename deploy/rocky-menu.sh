#!/bin/bash
# Source this from the Rocky installer. Values remain in the current shell.
rocky_menu() {
    local choice answer tag description state
    local -a items=()
    local subtitle="Rocky Linux ${VERSION_ID} | $(hostname) | HTTPS + local OS accounts"
    portal_url=${portal_url:-}
    manage_firewall=${manage_firewall:-1}
    selected_addons=${selected_addons:-}
    while true; do
        local address_label='Automatic DHCP/static address'
        [[ -z $portal_url ]] || address_label=$portal_url
        local firewall_label='Open HTTPS (443) with firewalld'
        [[ $manage_firewall == 1 ]] || firewall_label='Leave firewall management to you'
        choice=$(whiptail --title 'ServiceReady setup' --backtitle "$subtitle" --cancel-button 'Exit' --menu 'Configure your installation. Space toggles checklist items; Tab moves between buttons.' 22 78 8 \
            address "Portal address: $address_label" \
            firewall "Firewall: $firewall_label" \
            addons 'Select addons to install or update' \
            review 'Review configuration' \
            install 'Apply configuration and install' 3>&1 1>&2 2>&3) || return 1
        case "$choice" in
            address)
                answer=$(whiptail --title 'Portal address' --radiolist 'Automatic follows the current host address. A manual URL remains fixed.' 16 78 2 auto 'DHCP or static address on this machine' "$( [[ -z $portal_url ]] && echo ON || echo OFF )" manual 'Custom HTTPS hostname or address' "$( [[ -n $portal_url ]] && echo ON || echo OFF )" 3>&1 1>&2 2>&3) || continue
                if [[ $answer == auto ]]; then portal_url=''; else
                    answer=$(whiptail --title 'Custom portal URL' --inputbox 'Enter https://hostname or https://IP, on port 443.' 12 78 "${portal_url:-https://}" 3>&1 1>&2 2>&3) || continue
                    if ! python3 -c 'import sys; from urllib.parse import urlsplit; p=urlsplit(sys.argv[1]); sys.exit(not(p.scheme=="https" and p.hostname and p.port in (None,443) and not(p.path or p.query or p.fragment or p.username or p.password)))' "$answer"; then
                        whiptail --title 'Invalid address' --msgbox 'Use an HTTPS origin without a path or alternate port.' 10 76; continue
                    fi
                    portal_url=$answer
                fi ;;
            firewall)
                if whiptail --title 'Firewall' --yesno 'Allow this installer to open HTTPS port 443 using firewalld? Other addon ports remain closed. Choose No if you manage firewall rules yourself.' 13 78; then manage_firewall=1; else manage_firewall=0; fi ;;
            addons)
                items=()
                while IFS='|' read -r tag description; do
                    state=OFF
                    if printf '%s\n' "$selected_addons" | grep -qx "$tag"; then state=ON; fi
                    items+=("$tag" "$description" "$state")
                done <<'ADDONS'
host-tools|Host cleanup and OS-account terminal
downloads|Internal applications and tools
smtp-notifications|Application email into portal inboxes
snmp|SNMP monitoring and traps
voice|Phone and voice services
esxi|ESXi management
server-management|Service management links
ftp-updates|FTP update repository
pxe|PXE boot and image deployment
ADDONS
                answer=$(whiptail --title 'Addons' --separate-output --checklist 'Select packages to install/update. Unchecking an existing addon keeps it installed; remove addons in the portal.' 23 78 11 "${items[@]}" 3>&1 1>&2 2>&3) || continue
                selected_addons=$answer ;;
            review|install)
                local summary="Address: $address_label\nFirewall: $firewall_label\nAccounts: local Rocky accounts\nHTTPS: Nginx with a local CA\nAddons: ${selected_addons:-bare core only}\n\nExisting accounts and saved data are retained. Administrator credentials are requested in the console after package installation."
                if [[ $choice == review ]]; then whiptail --title 'Review installation' --msgbox "$summary" 22 78
                elif whiptail --title 'Apply installation' --yesno "$summary\n\nProceed?" 23 78; then return 0; fi ;;
        esac
    done
}
