import {expect,test} from "@playwright/test";

test("retry recovers from an unavailable graph",async ({page})=>{
 const graph={nodes:[],edges:[],min_similarity:.45,truncated:false,papers_considered:0};
 let available=false;
 await page.route("**/api/graph",r=>available
   ? r.fulfill({json:graph})
   : r.fulfill({status:503,json:{detail:"Graph unavailable"}}));
 await page.goto("/graph");
 const error=page.getByRole("alert").filter({hasText:"Graph unavailable"});
 await expect(error).toBeVisible();
 available=true;
 await page.getByRole("button",{name:"Try again"}).click();
 await expect(error).toHaveCount(0);
 await expect(page.getByText("No papers yet.",{exact:false})).toBeVisible();
});

test("explore a neighbor and filter weaker links",async ({page})=>{
 const nodes=["Alpha","Beta"].map(title=>({id:title,title,authors:["Ada"],year:2020,keywords:[],indexed:true}));
 const overview={nodes,edges:[],min_similarity:.45,truncated:false,papers_considered:2};
 await page.route("**/api/graph",r=>r.fulfill({json:overview}));
 await page.route("**/api/graph/*",r=>r.fulfill({json:{...overview,edges:[{source_paper_id:"Alpha",target_paper_id:"Beta",similarity_score:.8}]}}));
 await page.goto("/graph");
 await expect(page.getByRole("heading",{name:"Alpha",exact:true})).toBeVisible();
 await expect(page.getByRole("img",{name:/Related papers for Alpha/}).locator("canvas").first()).toBeVisible();
 await page.getByLabel("Semantic similarity links").uncheck();
 await expect(page.getByText("Semantic similarity links are hidden.")).toBeVisible();
 await page.getByLabel("Semantic similarity links").check();
 await page.getByRole("button",{name:"Explore Beta",exact:true}).press("Enter");
 await expect(page.getByRole("heading",{name:"Beta",exact:true})).toBeVisible();
 await expect(page.getByRole("link",{name:"Open original PDF"})).toHaveAttribute("href","/api/papers/Beta/pdf");
 await page.getByRole("slider").fill("0.9");
 await expect(page.getByText("No links meet this similarity threshold.")).toBeVisible();
});

test("open an older library paper outside the graph overview",async ({page})=>{
 const node=(id:string)=>({id,title:id,authors:[],year:null,keywords:[],indexed:true});
 const base={edges:[],min_similarity:.45,truncated:true,papers_considered:2};
 await page.route("**/api/status",r=>r.fulfill({json:{storage:"postgresql"}}));
 await page.route("**/api/papers?*",r=>r.fulfill({json:{items:[{...node("Archive"),filename:"archive.pdf",processing_status:"ready"}],total:1}}));
 await page.route("**/api/graph",r=>r.fulfill({json:{...base,nodes:[node("Recent"),node("New")]}}));
 await page.route("**/api/graph/Archive",r=>r.fulfill({json:{...base,nodes:[node("Archive"),node("Recent")],
   edges:[{source_paper_id:"Recent",target_paper_id:"Archive",similarity_score:.7}]}}));
 await page.goto("/search");
 await page.getByRole("link",{name:"Explore related papers for Archive"}).click();
 await expect(page.getByRole("heading",{name:"Archive",exact:true})).toBeVisible();
 await expect(page.getByRole("combobox")).toHaveValue("Archive");
 await expect(page.getByRole("button",{name:"Explore Recent"})).toBeVisible();
});
