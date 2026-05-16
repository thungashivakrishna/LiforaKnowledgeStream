import { test, expect } from '@playwright/test';

test.describe('KnowledgeStream Admin UI Audit', () => {
  const BASE_URL = 'http://localhost:3000';

  test('Navigate through all core modules and check for errors', async ({ page }) => {
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    // 1. Dashboard
    await page.goto(BASE_URL);
    await expect(page.locator('h1')).toContainText('Lifora');
    console.log('✅ Dashboard reached');

    // 2. Source Registry
    await page.click('text=Source Registry');
    await expect(page).toHaveURL(/.*sources/);
    console.log('✅ Source Registry functional');

    // 3. Knowledge Library
    await page.click('text=Documents');
    await expect(page).toHaveURL(/.*documents/);
    // Check if the "Knowledge Library" header is visible
    await expect(page.locator('h2')).toContainText('Knowledge Library');
    // Ensure no crash occurred (ChevronRight error would show up here)
    console.log('✅ Knowledge Library functional');

    // 4. Graph Explorer
    await page.click('text=Graph Explorer');
    await expect(page).toHaveURL(/.*graph/);
    // Wait for the force-graph canvas to potentially appear
    await page.waitForTimeout(2000);
    console.log('✅ Graph Explorer functional');

    // Final check for errors
    if (errors.length > 0) {
      console.error('❌ UI Errors Detected:', errors);
      throw new Error(`UI Audit Failed with ${errors.length} console/page errors.`);
    }
  });
});
