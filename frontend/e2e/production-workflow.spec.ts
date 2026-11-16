import { expect, test } from '@playwright/test'

for (const rework of [false, true]) {
  test(`production through QC, QA and delivery${rework ? ' with rejected correction' : ''}`, async ({ page }) => {
    await page.goto('/e2e/workflow.html')
    await page.getByRole('button', { name: 'Start Work', exact: true }).click()
    await page.getByRole('button', { name: 'Complete File', exact: true }).click()
    await page.locator('.isa-form').getByRole('button', { name: 'Complete File', exact: true }).click()
    await expect(page.getByLabel('Production quantity')).toHaveText('3')
    await page.getByLabel('Acting role').selectOption('qc')
    await page.getByRole('button', { name: 'Start QC', exact: true }).click()
    await page.getByRole('button', { name: 'Complete QC', exact: true }).click()
    if (rework) {
      await page.getByLabel('Result').selectOption('rejected')
      await page.getByLabel('Comments').fill('Correct the roof geometry')
    }
    await page.getByRole('button', { name: 'Save QC Result' }).click()
    if (rework) {
      await page.getByLabel('Acting role').selectOption('prod')
      await page.getByRole('button', { name: 'Start Rework', exact: true }).click()
      await page.getByRole('button', { name: 'Complete Rework', exact: true }).click()
      await page.locator('.isa-form').getByRole('button', { name: 'Complete Rework', exact: true }).click()
      await expect(page.getByLabel('Production quantity')).toHaveText('3')
      await page.getByLabel('Acting role').selectOption('qc')
      await page.getByRole('button', { name: 'Start QC', exact: true }).click()
      await page.getByRole('button', { name: 'Complete QC', exact: true }).click()
      await page.getByRole('button', { name: 'Save QC Result' }).click()
    }
    await page.getByLabel('Acting role').selectOption('qa')
    await page.getByRole('button', { name: 'Start QA', exact: true }).click()
    await page.getByRole('button', { name: 'Complete QA', exact: true }).click()
    await page.getByRole('button', { name: 'Save QA Result' }).click()
    await page.getByLabel('Acting role').selectOption('tl')
    await page.getByRole('button', { name: 'Mark Ready', exact: true }).click()
    page.once('dialog', dialog => dialog.accept('QA delivery reference'))
    await page.getByRole('button', { name: 'Mark Delivered', exact: true }).click()
    await expect(page.getByLabel('Delivery status')).toHaveText('delivered')
    await expect(page.getByLabel('Production quantity')).toHaveText('3')
  })
}

test('missing source plan can be corrected before allocation', async ({ page }) => {
  await page.goto('/e2e/workflow.html?draft=true')
  await page.getByRole('button', { name: 'Start Work', exact: true }).waitFor()
  await page.getByLabel('Acting role').selectOption('tl')
  const plan = page.getByRole('form', { name: 'Plan for file DRAFT' })
  await plan.getByLabel('Planned quantity').fill('1250')
  await plan.getByLabel('Planned unit').fill('m')
  await plan.getByRole('button', { name: 'Save file plan' }).click()
  await expect(plan).toHaveCount(0)
  await expect(page.getByText('Complete missing file plans')).toHaveCount(0)
})
