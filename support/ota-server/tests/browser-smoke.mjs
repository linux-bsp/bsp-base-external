// Optional real-browser smoke test. Use a disposable OTA feed: this publishes a version.
// CHROMIUM_BIN=/path/to/chrome node tests/browser-smoke.mjs URL BUNDLE OUTPUT_DIR
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp, readFile, writeFile, mkdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';

const [url, bundle, outputDir] = process.argv.slice(2);
assert(url && bundle && outputDir && process.env.CHROMIUM_BIN,
    'Provide URL, BUNDLE, OUTPUT_DIR and CHROMIUM_BIN');
await mkdir(outputDir, {recursive: true});
const profile = await mkdtemp(join(tmpdir(), 'ota-browser-'));
const browser = spawn(process.env.CHROMIUM_BIN, [
    '--headless', '--no-sandbox', '--disable-dev-shm-usage', '--no-proxy-server',
    '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
    `--user-data-dir=${profile}`, 'about:blank',
], {stdio: ['ignore', 'ignore', 'ignore']});
let ws;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label, timeout=60000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
        const result = await fn();
        if (result) return result;
        await pause(100);
    }
    throw new Error(`Timed out: ${label}`);
}
try {
    const port = await until(async()=>{
        try { return (await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]; }
        catch { assert(browser.exitCode === null, 'Browser exited'); return null; }
    }, 'DevTools startup');
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method:'PUT'})).json();
    ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
    let sequence=0;
    const pending = new Map();
    const errors = [];
    ws.onmessage = event=>{
        const message=JSON.parse(event.data);
        if(message.id){
            const request=pending.get(message.id);if(!request)return;
            pending.delete(message.id);clearTimeout(request.timer);
            if(message.error)request.reject(new Error(JSON.stringify(message.error)));
            else request.resolve(message.result);
        } else if(message.method==='Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    };
    function rpc(method,params={}){
        return new Promise((resolve,reject)=>{
            const id=++sequence;
            const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},30000);
            pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
        });
    }
    async function evaluate(expression){
        const result=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
        if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
        return result.result.value;
    }
    await rpc('Runtime.enable');await rpc('Page.enable');
    await rpc('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
    const seeded=await fetch(url+'/api/devices/browser-test',{method:'POST',headers:{'X-OTA-Request':'1'},
        body:'BSPOTASTATE1 browser-test ti-am62x am62x-sd-ab-v1 1 65537 test-boot success 1 65537\n'});
    assert.equal(seeded.status,200,'Device report should be persisted');
    for (const phase of ['installing','install-failed']) {
        const r=await fetch(url+'/api/devices/browser-test',{method:'POST',headers:{'X-OTA-Request':'1'},
            body:`BSPOTASTATE1 browser-test ti-am62x am62x-sd-ab-v1 2 65538 next-boot ${phase} 0 65537\n`});
        assert.equal(r.status,200);
    }
    await rpc('Page.navigate',{url});
    await until(()=>evaluate("document.querySelector('#current-version')?.textContent !== '加载中…' && !!document.querySelector('#firmware')"),'page state');
    await until(()=>evaluate("document.querySelector('#devices')?.textContent.includes('browser-test') && document.querySelector('#devices').textContent.includes('升级成功')"),'device result table');
    assert.equal(await evaluate("document.querySelectorAll('#devices tr').length"),2);
    await evaluate("document.querySelector('#devices details').open=true");
    assert(await evaluate("document.querySelector('#devices details').textContent.includes('正在安装') && document.querySelector('#devices details').textContent.includes('安装失败')"));
    const before=await (await fetch(url+'/api/state')).json();
    const doc=await rpc('DOM.getDocument');
    const input=await rpc('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#firmware'});
    await rpc('DOM.setFileInputFiles',{nodeId:input.nodeId,files:[resolve(bundle)]});
    await until(()=>evaluate("!document.querySelector('#upload-button').disabled"),'file selection');
    await evaluate("document.querySelector('#upload-button').click()");
    await until(()=>evaluate("document.querySelector('#upload-status').textContent.includes('已保存为待发布')"),'upload and validation');
    const uploaded=await (await fetch(url+'/api/state')).json();
    assert.equal(uploaded.latest,before.latest,'Upload must not publish');
    const draft=uploaded.drafts.find(d=>!before.drafts.some(old=>old.id===d.id));
    assert(draft && !draft.publication,'New draft should be unpublished');
    assert.equal(draft.firmware_version,'1.0.1');
    async function screenshot(name){
        const {data}=await rpc('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        await writeFile(join(outputDir,name),Buffer.from(data,'base64'));
    }
    await screenshot('uploaded-desktop.png');
    await evaluate(`document.querySelector('[data-publish="${draft.id}"]').click()`);
    await until(()=>evaluate("document.querySelector('#notice').textContent.startsWith('已发布 #')"),'publish button');
    await until(async()=>{
        const state=await (await fetch(url+'/api/state')).json();
        return state.latest>before.latest;
    },'latest publication');
    await until(()=>evaluate("document.querySelector('#current-version').textContent==='1.0.1' && !document.querySelector('[data-publish]')"),'published UI');
    const after=await (await fetch(url+'/api/state')).json();
    await screenshot('published-desktop.png');
    await rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await pause(150);
    assert(await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),'Mobile page overflows');
    await screenshot('published-mobile.png');
    assert.equal(errors.length,0,JSON.stringify(errors));
    await writeFile(join(outputDir,'browser-result.json'),JSON.stringify({
        uploadCreatedDraft:true,uploadDidNotPublish:true,deviceResultsRendered:true,publication:after.latest,
        firmwareVersion:'1.0.1',mobileNoOverflow:true,javascriptErrors:errors,
    },null,2)+'\n');
    console.log('PASS: Chromium file upload -> unpublished draft -> publish; desktop/mobile UI and JS verified');
} finally {
    if(ws)ws.close();
    browser.kill('SIGTERM');
    await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else browser.once('exit',resolve);});
    await rm(profile,{recursive:true,force:true});
}
