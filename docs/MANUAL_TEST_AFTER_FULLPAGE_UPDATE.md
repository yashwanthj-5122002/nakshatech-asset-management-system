# Manual Test After the Full-page Update

## Login
- IT: `it@nakshatech.com` / `IT@123456`
- Management: `management@nakshatech.com` / `Manager@123`

## Test 1: Add one system
1. Open Asset Register.
2. Click **Add IT Asset**.
3. Confirm a full page opens at `/assets/new`; no popup and no tabs.
4. Enter:
   - CPU / Asset Tag: `QA-CPU-3953`
   - Workstation: `QA-NW045`
   - Device: Computer
   - Status: Available
   - Used By: blank
   - Department: IT
   - Mouse: `QA-MOUSE-7349`
   - Keyboard: `QA-KB-6120`
   - Memory: `8 GB`
   - SSD: `256 GB`
   - Network: DHCP
5. Save.
6. Expected: one record is created and the dashboard total increases by one.

## Test 2: Replace the mouse
1. Open the new asset.
2. Click **Change Component**.
3. Work Records opens in Component / Configuration Change mode with the asset selected.
4. Select Mouse.
5. Confirm current value is `QA-MOUSE-7349`.
6. Enter new value `QA-MOUSE-8201` and reason `Old mouse button failed`.
7. Save.
8. Expected:
   - Asset Register now shows mouse `QA-MOUSE-8201`.
   - Old mouse `QA-MOUSE-7349` remains in component history.
   - A completed IT work record is created automatically.

## Test 3: Verify both Excel files
1. Open Excel & Reports.
2. Download **NakshaTech Asset Details**.
3. Find `QA-CPU-3953`.
4. Expected: MOUSE column contains only `QA-MOUSE-8201`.
5. Download **Replacement History Excel**.
6. Expected Component Replacements row:
   - CPU Tag: `QA-CPU-3953`
   - Workstation: `QA-NW045`
   - Component: Mouse
   - Old: `QA-MOUSE-7349`
   - New: `QA-MOUSE-8201`

## Test 4: Old tag was not recorded
1. Edit the test asset and clear Keyboard tag, then save.
2. Open Change Component and choose Keyboard.
3. Enter new tag `QA-KB-9001`.
4. Expected replacement history: `Not Previously Recorded -> QA-KB-9001`.
5. Expected Asset Register: current keyboard is `QA-KB-9001`.

## Test 5: Complete CPU replacement
1. Create another available computer with CPU tag `QA-CPU-4501`.
2. Assign the old system `QA-CPU-3953` to a test employee and workstation `QA-NW045`.
3. Create a normal inspection Work Record and complete it with motherboard failure.
4. Open Replacements.
5. Select old CPU `QA-CPU-3953 / QA-NW045` and new CPU `QA-CPU-4501`.
6. Submit.
7. Login as Management and approve.
8. Expected:
   - Old CPU status: Replaced.
   - New CPU status: Assigned.
   - New CPU receives the employee, department and workstation.
   - New CPU keeps its own processor, memory, MAC, system name and price.
   - Complete Asset Replacements sheet records old CPU -> new CPU.

## Pass rule
The update passes when:
- Add Asset is a full page, not a popup.
- CPU Tag and Workstation are shown first.
- Current Asset Excel always shows the latest current value.
- Separate Replacement History Excel shows old and new values.
- No component change creates a duplicate computer record.
- Complete CPU replacement preserves the old asset history.
