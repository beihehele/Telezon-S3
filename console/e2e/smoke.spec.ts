import { test, expect } from '@playwright/test'

test('login page loads', async ({ page }) => {
  await page.goto('./#/login')
  await expect(page.getByText('Telezon')).toBeVisible()
})

test.describe('authenticated', () => {
  test.skip(
    !process.env.CONSOLE_E2E_USER || !process.env.CONSOLE_E2E_PASSWORD,
    'Set CONSOLE_E2E_USER and CONSOLE_E2E_PASSWORD',
  )

  test('login and open files', async ({ page }) => {
    await page.goto('./#/login')
    await page.locator('#login-username').fill(process.env.CONSOLE_E2E_USER!)
    await page.locator('#login-password').fill(process.env.CONSOLE_E2E_PASSWORD!)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByText('全部文件')).toBeVisible({ timeout: 15_000 })
  })
})
