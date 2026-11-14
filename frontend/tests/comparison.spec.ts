import { expect, test } from "@playwright/test";

test("compare selected papers and inspect a cell's source", async ({page}) => {
  const papers = ["Alpha", "Beta"].map(title => ({
    title, id: title, authors: [], filename: title + ".pdf", processing_status: "ready",
  }));
  await page.route("**/api/status", route => route.fulfill({json: {storage: "postgresql"}}));
  await page.route("**/api/papers?*", route => route.fulfill({json: {items: papers, total: 2}}));
  await page.route("**/api/compare", route => {
    const body = route.request().postDataJSON();
    expect(body.paper_ids).toEqual(["Alpha", "Beta"]);
    return route.fulfill({json: {dimension: body.dimension, cells: [
      {paper_id: "Alpha", title: "Alpha", answer: {answer: "Controlled experiment [1]", citations: [
        {source: 1, paper_id: "Alpha", paper_title: "Alpha", page: 2, snippet: "A controlled experiment."},
      ]}},
      {paper_id: "Beta", title: "Beta", answer: {answer: "Insufficient evidence.", citations: []}},
    ]}});
  });
  await page.goto("/search");
  await page.getByRole("tab", {name: "Compare papers"}).click();
  const run = page.getByRole("button", {name: "Compare selected papers"});
  await expect(run).toBeDisabled();
  for (const title of ["Alpha", "Beta"]) {
    const checkbox = page.getByRole("checkbox", {name: new RegExp(title)});
    await checkbox.click();
    await expect(checkbox).toBeChecked();
  }
  await run.click();
  await expect(page.getByRole("cell", {name: "Insufficient evidence."})).toBeVisible();
  await page.getByRole("button", {name: "[1] Page 2"}).click();
  await expect(page.getByRole("link", {name: "Open original PDF"})).toHaveAttribute("href", "/api/papers/Alpha/pdf#page=2");
  await page.getByRole("button", {name:"Close evidence"}).click();
  await page.getByRole("checkbox", {name: /Alpha/}).click();
  await expect(page.getByRole("checkbox", {name: /Alpha/})).not.toBeChecked();
  await expect(page.getByRole("table")).toHaveCount(0);
});
