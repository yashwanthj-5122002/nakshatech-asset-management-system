# Local Backup Manual Test

1. Confirm the deployed login page opens over HTTPS.
2. Run the local agent installer as Administrator.
3. Confirm four current workbooks exist under `E:\NakshaTech_Backups`.
4. Open each workbook and confirm its Backup Summary role and reporting month.
5. Add one test IT record and one test Drone record in the normal software.
6. Run the hourly task manually from Task Scheduler or run the installed script with `-Mode Backup`.
7. Confirm the current files were replaced and the test records appear in the correct workbooks.
8. Temporarily stop the backend or block the API.
9. Wait for the five-minute health task.
10. Confirm a new `Crash_Reports\Incident_*` folder contains a crash report and copies of the latest valid workbooks.
11. Restore the backend.
12. Confirm the report records recovery and all current workbooks refresh.
13. Test month rollover in a staging environment by changing the test clock or filenames; never alter the production clock.
