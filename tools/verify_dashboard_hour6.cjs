const {chromium}=require('C:/Users/User1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8503/');await page.getByRole('heading',{name:'Мониторинг по входным измерениям'}).waitFor({timeout:30000});
  for(let hour=1;hour<=6;hour++){
   await page.getByRole('button',{name:'＋1 час',exact:true}).click();
   await page.getByText(`Текущий час: ${String(hour).padStart(2,'0')}:00`,{exact:true}).waitFor({timeout:120000});
  }
  await page.getByText(/К возможному началу эффекта в 07:00 ожидается недобор 0.83 т/).waitFor({timeout:120000});
  const text=await page.locator('body').innerText();
  if(text.includes('maximum_change')||text.includes('только из opportunities'))throw Error('Internal English terms remain visible');
  const tables=await page.locator('.readable-table').count();
  const exceptions=await page.locator('[data-testid="stException"]').allTextContents();
  if(!tables||exceptions.length||errors.length)throw Error(JSON.stringify({tables,exceptions,errors}));
  await page.screenshot({path:'data/dashboard-hour6-readable-20260921.png',fullPage:true});
  console.log(JSON.stringify({hour:'06:00',readableTables:tables,streamlitExceptions:0,pageErrors:0}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
