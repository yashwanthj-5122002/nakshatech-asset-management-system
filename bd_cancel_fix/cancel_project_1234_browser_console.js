// Run only in the browser where you are logged into NakshaTech ERP
// as the expense owner, Finance or Admin. Never share your session token.
(async () => {
  const projectId = 1;
  const expectedCode = 'PEXP-20261030-4EBCF78F0C';
  const token = localStorage.getItem('asset_token') || sessionStorage.getItem('asset_token');
  if (!token) throw new Error('Log in again: ERP session token not found.');
  const headers = {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'};
  const listResponse = await fetch(`/api/commercial/expenses?project_id=${projectId}`, {headers});
  const data = await listResponse.json();
  if (!listResponse.ok) throw new Error(JSON.stringify(data));
  const expense = data.find(item => item.expense_code === expectedCode && item.project_id === projectId);
  if (!expense) throw new Error('Matching expense not found. No changes made.');
  console.table({code: expense.expense_code, id: expense.id, status: expense.status, amount: expense.amount, employee_id: expense.employee_id});
  if (expense.status !== 'DRAFT') throw new Error('Expense is no longer DRAFT. Stop and investigate.');
  if (!confirm(`CANCEL DRAFT EXPENSE ${expense.expense_code} for Project 1234? This is an audited financial action.`)) return;
  const reason = prompt('Enter the actual business reason for cancellation (10+ characters):');
  if (!reason || reason.trim().length < 10) throw new Error('Cancelled: reason is required. No changes made.');
  const response = await fetch(`/api/commercial/expenses/${expense.id}/cancel`, {
    method: 'POST', headers, body: JSON.stringify({reason: reason.trim()})
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(JSON.stringify(result));
  console.log('Cancellation saved:', result.expense_code, result.status);
  alert(`Expense ${result.expense_code} is now ${result.status}. Refresh Finance Closure.`);
})().catch(err => { console.error(err); alert(`Cancellation failed: ${err.message}`); });
