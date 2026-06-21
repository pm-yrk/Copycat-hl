# Copycat snapshot publisher autostart

Adds a Windows startup task for the local snapshot publisher.

## Install

```cmd
cd /d "%USERPROFILE%\OneDrive\Desktop\hyper_wallet_tracker_saas_v1\scripts\local_snapshot_publisher"
install_windows_startup_task.cmd
```

Start it immediately:

```cmd
start_snapshot_publisher_background.cmd
```

Open logs:

```cmd
open_publisher_log.cmd
```

Keep `publisher.env` private. It is ignored by Git.
