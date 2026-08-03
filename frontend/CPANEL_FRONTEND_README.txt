NAKSHATECH CRM FRONTEND - CPANEL STATIC DEPLOYMENT
=================================================

The frontend uses same-origin API calls through /api.
The included .htaccess preserves React routes and excludes /api from SPA rewrites.

Windows build (recommended on the working PC):
  Double-click BUILD_CPANEL_FRONTEND_WINDOWS.cmd

It creates:
  NakshaTech-CRM-Frontend-Upload.zip

Upload that generated ZIP to:
  /home/nakshatechws/crm.nakshatech.com

Extract the CONTENTS there so index.html is directly inside the subdomain folder.
Do not upload node_modules or the frontend source to the public folder.
