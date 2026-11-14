import {test,expect} from "@playwright/test";

test("go from the landing page through a paper record to a scoped question",async({page})=>{
 const id="a20d1297-857f-41bd-a367-6db45a704dfa";
 const paper={id,title:"Water delivery",filename:"test.pdf",authors:["Ada"],abstract:"A study of drip lines.",publication_year:2024,processing_status:"ready"};
 await page.route("**/api/status",r=>r.fulfill({json:{storage:"postgresql",answer_model:"test"}}));
 await page.route("**/api/papers?*",r=>r.fulfill({json:{items:[paper],total:1}}));
 await page.route(`**/api/papers/${id}?*`,r=>r.fulfill({json:{...paper,chunk_count:3,uploaded_at:"2026-01-01",metadata_json:{page_count:2,sections:["Methods"]}}}));
 await page.route(`**/api/graph/${id}`,r=>r.fulfill({json:{nodes:[paper],edges:[]}}));
 await page.goto("/");
 await page.getByRole("link",{name:"Add research papers →"}).click();
 await page.getByRole("link",{name:"Read paper →"}).click();
 await expect(page.getByRole("heading",{name:"Water delivery"})).toBeVisible();
 await expect(page.getByText("Methods",{exact:true})).toBeVisible();
 await page.getByRole("link",{name:"Ask ScholarGraph"}).click();
 await page.route("**/api/chat/query",r=>{
   expect(r.request().postDataJSON().paper_ids).toEqual([id]);
   return r.fulfill({json:{answer:"Water flows through drip lines.",citations:[],latency_ms:50,insufficient_evidence:false}});
 });
 await page.getByLabel("Research question").fill("How is water delivered?");
 await page.getByRole("button",{name:"Ask question ↗"}).click();
 await expect(page.getByText("Water flows through drip lines.")).toBeVisible();
});

test("search diagnostics and historical evaluation baselines are inspectable",async({page})=>{
 await page.route("**/api/status",r=>r.fulfill({json:{storage:"postgresql"}}));
 await page.route("**/api/papers?*",r=>r.fulfill({json:{items:[],total:0}}));
 await page.route("**/api/search",r=>{
   expect(r.request().postDataJSON().diagnostics).toBe(true);
   return r.fulfill({json:{latency_ms:4,results:[{paper_id:"p",chunk_id:"c",title:"Test",snippet:"text",page:1,score:0.01,score_type:"rrf",diagnostics:{dense_rank:2}}]}});
 });
 await page.goto("/search");
 await page.getByLabel("Show retrieval diagnostics").check();
 await page.getByLabel("Search query").fill("ranking");
 await page.getByRole("button",{name:"Search ↗",exact:true}).click();
 await expect(page.getByText("dense rank: 2",{exact:true})).toBeVisible();
 await page.getByRole("link",{name:"Evaluation",exact:true}).click();
 await expect(page.getByRole("table",{name:"Retrieval results by method"})).toBeVisible();
 await expect(page.getByText("5 / 6")).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
