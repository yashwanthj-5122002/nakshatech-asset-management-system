# Employee Master management control

The Excel workbook is uploaded from **Management → Employee Data Control**. The server checks the eight expected columns, duplicate identifiers, required fields, phone numbers and departments. Preview does not write to the database. Import writes validated rows to the ERP database and leaves the Excel directory **private**. The uploaded workbook is not added to the repository or retained as an application file.

Management can review all imported rows privately and then publish them. Publication allows the Software Team Employee Master directory to return the imported rows and permits those employees to start or finish self-registration. **Stop sharing** hides the imported rows from that directory and blocks new or in-progress self-registration. Management-approved new joiners are separate and remain available through their onboarding workflow.

**Delete imported records** removes Excel-imported rows from the live `employee_master` table and turns publication off. It does not delete existing ERP user accounts, their copied profile fields, tickets, audit records, or database backups. Retention and removal of those records require their own reviewed process. The action requires typing `DELETE EMPLOYEE MASTER` and is audited without storing workbook contents in the audit record.

The publication switch starts private for existing imported rows on upgrade. The new `employee_master_publication` table is created by the application's normal `create_all` startup; `backend/migrations/20260929_employee_master_management_publication.sql` is provided for deployments that apply SQL migrations directly. The command line import also returns the directory to private review.
