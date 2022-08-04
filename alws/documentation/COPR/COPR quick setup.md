## Quick setup for COPR plugin

1. Install core dnf plugins that contains COPR plugin

    ```
    dnf install dnf-plugins-core
    ```

2. Download AlmaLinux configuration file in your system

    ```
    curl -o /etc/dnf/plugins/copr.d/almalinux.conf https://raw.githubusercontent.com/AlmaLinux/albs-web-server/master/reference_data/almalinux.conf
    ```