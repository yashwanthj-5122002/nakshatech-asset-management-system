# Deployment and Local PC Installation

## 1. Configure the deployed backend

Generate a token by running:

`GENERATE_BACKUP_AGENT_TOKEN_WINDOWS.cmd`

Configure these production environment values in cPanel/backend hosting:

```env
BACKUP_TIMEZONE=Asia/Kolkata
LOCAL_BACKUP_AGENT_ENABLED=true
LOCAL_BACKUP_AGENT_TOKEN=<generated token>
```

Restart the backend application after setting the values.

The expected protected endpoints are:

- `https://YOUR-SUBDOMAIN/api/local-backup/health`
- `https://YOUR-SUBDOMAIN/api/local-backup/export.xlsx?role=it`

Do not expose or email the token. Do not commit it to Git.

## 2. Install on the designated NakshaTech backup PC

PC confirmed for this deployment:

- Computer: `DESKTOP-SF003TK`
- Windows: Windows 10 Pro 64-bit
- Backup drive: E:
- Available capacity reported: 2387.3 GB

After the subdomain is live, right-click and run as Administrator:

`INSTALL_LOCAL_BACKUP_AGENT_WINDOWS.cmd`

Enter:

1. Deployed HTTPS application URL.
2. API URL, normally the suggested `/api` URL.
3. `E:\NakshaTech_Backups`.
4. The same deployment token.

The installer creates:

- `NakshaTech Local Backup Health` scheduled task: every 5 minutes.
- `NakshaTech Local Backup Hourly` scheduled task: every hour at minute 55.
- A public Desktop shortcut named `NakshaTech Backups`.
- The first validated set of workbooks.

## 3. Local storage layout

```text
E:\NakshaTech_Backups
├── IT
│   ├── Current
│   └── Monthly
├── Drone
│   ├── Current
│   └── Monthly
├── Management
│   ├── Current
│   └── Monthly
├── Admin
│   ├── Current
│   └── Monthly
├── Crash_Reports
└── Logs
```

## 4. Important limitation

When the deployed API/database is already unreachable, it cannot generate a new workbook at that exact moment. The crash package therefore preserves the latest previously validated hourly workbooks and records the outage. The agent refreshes immediately after recovery.
