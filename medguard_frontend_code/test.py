import json, asyncio
from playwright.async_api import async_playwright
SAMPLE={"resolved":[{"input":"Coumadin","name":"warfarin","method":"rxnorm"},{"input":"ibuprofen","name":"ibuprofen","method":"exact"},{"input":"Lipitor","name":"atorvastatin","method":"rxnorm"},{"input":"Prozac","name":"fluoxetine","method":"rxnorm"},{"input":"madeupxyz","name":None,"method":"no_match"}],
"verified":[
 {"pair_key":"ibuprofen|warfarin","status":"verified","evidence":{"drug_a":"Ibuprofen","drug_b":"Warfarin","level":"Major"}},
 {"pair_key":"fluoxetine|warfarin","status":"verified","evidence":{"drug_a":"Fluoxetine","drug_b":"Warfarin","level":"Moderate"}},
 {"pair_key":"atorvastatin|warfarin","status":"verified","evidence":{"drug_a":"Atorvastatin","drug_b":"Warfarin","level":"Minor"}},
 {"pair_key":"fluoxetine|ibuprofen","status":"verified_unclassified","evidence":{"drug_a":"Fluoxetine","drug_b":"Ibuprofen"}},
 {"pair_key":"atorvastatin|ibuprofen","status":"not_covered","reason":"no record in DDInter"},
 {"pair_key":"atorvastatin|fluoxetine","status":"not_covered","reason":"no record in DDInter"}],
"answer":"Ibuprofen and warfarin: Major.\n\nFluoxetine and warfarin: Moderate.\n\nAtorvastatin pairs are not covered.",
"estimates":{"atorvastatin|ibuprofen":{"drug_a":"atorvastatin","drug_b":"ibuprofen","level":"Moderate","explanation":"Why caution\nI do not know of a well-established interaction.\n\nPossible effects\n- Not known\n\nWhy this matters\nNot being covered does not mean safe.\n\nWhat to do\nAsk a physician or pharmacist."}}}
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path="/opt/pw-browsers/chromium") if False else await p.chromium.launch()
        errs=[]
        for name,vp in [("desktop",{"width":1280,"height":900}),("mobile",{"width":390,"height":844})]:
            ctx=await b.new_context(viewport=vp)
            pg=await ctx.new_page()
            pg.on("pageerror",lambda e:errs.append(("pageerror",str(e))))
            pg.on("console",lambda m:errs.append(("console",m.text)) if m.type=="error" and "fonts.g" not in m.text and "ERR_" not in m.text else None)
            async def h(route):
                u=route.request.url
                if route.request.method=="POST" and u.rstrip("/").endswith("amazonaws.com"):
                    await route.fulfill(status=200,content_type="application/json",body=json.dumps(SAMPLE),headers={"access-control-allow-origin":"*"})
                elif "execute-api" in u: await route.abort()
                elif "fonts.g" in u: await route.abort()
                else: await route.continue_()
            await pg.route("**/*",h)
            await pg.goto("file:///home/claude/site/index.html")
            await pg.wait_for_timeout(900)
            await pg.screenshot(path=f"shot_{name}_home.png")
            await pg.click("[data-ex*=Coumadin]")
            await pg.wait_for_selector(".alert",timeout=8000)
            await pg.wait_for_timeout(1500)
            await pg.screenshot(path=f"shot_{name}_results.png",full_page=True)
            # open pair popup
            await pg.click(".row >> nth=0"); await pg.wait_for_timeout(600)
            await pg.screenshot(path=f"shot_{name}_pair.png")
            await pg.keyboard.press("Escape"); await pg.wait_for_timeout(400)
            # save list
            await pg.click("text=Save this combination as a list"); await pg.wait_for_timeout(500)
            await pg.fill("#lname","Test regimen"); 
            await pg.screenshot(path=f"shot_{name}_save.png")
            await pg.click("dialog >> button:has-text('Save list')"); await pg.wait_for_timeout(700)
            await pg.evaluate("document.querySelector('[data-nav=lists]').click()"); await pg.wait_for_timeout(900)
            await pg.screenshot(path=f"shot_{name}_lists.png",full_page=True)
            await pg.click("text=Submit for review"); await pg.wait_for_timeout(500)
            await pg.click("dialog >> button:has-text('Submit for review')"); await pg.wait_for_timeout(1200)
            txt=await pg.inner_text("#listGrid")
            print(name,"after submit:", "Waiting for review" in txt)
            # reviewer flow x2
            await pg.evaluate("document.querySelector('[data-nav=review]').click()"); await pg.wait_for_timeout(500)
            for who in ["Dr A","Dr B"]:
                await pg.evaluate("document.getElementById('signBtn').click()"); await pg.wait_for_timeout(500)
                await pg.fill("#rname",who); await pg.fill("#rcode","x"); await pg.click("dialog >> button:has-text('Sign in')"); await pg.wait_for_timeout(900)
                if who=="Dr A": await pg.screenshot(path=f"shot_{name}_review.png",full_page=True)
                await pg.click(".review-card >> button:has-text('Approve')"); await pg.wait_for_timeout(500)
                await pg.click("dialog >> button:has-text('Approve')"); await pg.wait_for_timeout(1000)
                await pg.evaluate("document.getElementById('signBtn').click()"); await pg.wait_for_timeout(400)
            await pg.evaluate("document.querySelector('[data-nav=lists]').click()"); await pg.wait_for_timeout(1500)
            txt=await pg.inner_text("#listGrid")
            print(name,"verified after 2 reviewers:", "Verified by reviewers" in txt)
            await pg.screenshot(path=f"shot_{name}_verified.png",full_page=True)
            await ctx.close()
        print("errors:",errs)
        await b.close()
asyncio.run(main())
