import { expect, test } from "@playwright/test";

test("paper scope and research mode survive navigation, history, and reload", async ({page}) => {
  const ids = ["a20d1297-857f-41bd-a367-6db45a704dfa", "b20d1297-857f-41bd-a367-6db45a704dfa"];
  const params = ids.map(id => "paper=" + id).join("&");
  await page.route("**/api/status", r => r.fulfill({json:{storage:"postgresql"}}));
  await page.route("**/api/papers?*", r => r.fulfill({json:{items:[],total:0}}));
  await page.route("**/api/chat/query", r => r.fulfill({json:{answer:"Scoped response",citations:[],latency_ms:1}}));
  await page.goto("/search?" + params);
  await page.getByRole("tab",{name:/Ask your library/}).click();
  await expect(page).toHaveURL(url => url.pathname === "/chat" && url.search.slice(1) === params);
  await page.goBack();
  await expect(page.getByLabel("Search query")).toBeVisible();
  await page.goForward();
  await page.reload();
  const navigation = page.getByRole("navigation",{name:"Main navigation"});
  for (const [label,path] of [["Library","/library"],["Search","/search"],["Compare","/compare"],["Chat","/chat"]]) {
    await navigation.getByRole("link",{name:label,exact:true}).click();
    await expect(page).toHaveURL(url => url.pathname === path && url.search.slice(1) === params);
  }
  await expect(navigation.getByRole("link",{name:"Graph",exact:true})).toHaveAttribute("href","/graph");
  await page.getByLabel("Research question").fill("Which studies investigated retrieval?");
  const outgoing = page.waitForRequest(req => new URL(req.url()).pathname === "/api/chat/query");
  await page.getByRole("button",{name:"Ask question ↗"}).click();
  expect((await outgoing).postDataJSON().paper_ids).toEqual(ids);
  await page.getByRole("button",{name:"Clear 2 selected"}).click();
  await expect(page).toHaveURL(url => url.pathname === "/chat" && !url.searchParams.has("paper"));
});

test("a pending deletion preserves papers selected in the meantime", async ({page}) => {
  const papers = ["A","B"].map(id => ({id,title:"Study " + id,authors:[],filename:id+".pdf",processing_status:"ready"}));
  await page.route("**/api/status", r => r.fulfill({json:{storage:"postgresql"}}));
  await page.route("**/api/papers?*", r => r.fulfill({json:{items:papers,total:papers.length}}));
  let finish!: () => void;
  const pending = new Promise<void>(resolve => {finish = resolve});
  await page.route("**/api/papers/A", async r => {
    await pending;
    papers.shift();
    await r.fulfill({status:204});
  });
  await page.goto("/search?paper=A");
  page.once("dialog", dialog => dialog.accept());
  const request = page.waitForRequest(req => req.method() === "DELETE");
  await page.getByRole("button",{name:"Delete Study A"}).click();
  await request;
  try {
    const checkbox = page.getByRole("checkbox",{name:/Study B/});
    await checkbox.click();
    await expect(checkbox).toBeChecked();
    await expect(page).toHaveURL(url => url.searchParams.getAll("paper").join(",") === "A,B");
  } finally { finish(); }
  await expect(page).toHaveURL(url => url.pathname === "/search" && url.searchParams.getAll("paper").join(",") === "B");
  await expect(page.getByRole("checkbox",{name:/Study B/})).toBeChecked();
  await expect(page.getByRole("button",{name:"Delete Study A"})).toHaveCount(0);
});

test("library failure offers retry and shows empty state only after successful load", async ({page}) => {
  await page.route("**/api/status", r => r.fulfill({json:{storage:"postgresql"}}));
  let available = false;
  await page.route("**/api/papers?*", r => available
    ? r.fulfill({json:{items:[],total:0}})
    : r.fulfill({status:503,json:{detail:"Database unavailable"}}));
  await page.goto("/library");
  await expect(page.getByRole("alert").filter({hasText:"Database unavailable"})).toBeVisible();
  await expect(page.getByText("Upload a PDF to start your library.")).toHaveCount(0);
  await expect(page.getByText("Your reading list starts here.",{exact:false})).toHaveCount(0);
  available = true;
  await page.getByRole("button",{name:"Retry library"}).click();
  await expect(page.getByText("Upload a PDF to start your library.")).toBeVisible();
  await expect(page.getByRole("alert").filter({hasText:"Database unavailable"})).toHaveCount(0);
});
